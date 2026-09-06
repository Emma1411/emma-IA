import json
import logging
import os
from typing import Any, Dict, List

from openai import OpenAI

from app.config import settings


logger = logging.getLogger(__name__)


class EmmaIA:

    CHAMPS_OBLIGATOIRES_SORTIE = [
        "statut_dossier",
        "niveau_confiance",
        "informations_verifiees",
        "metriques_officielles",
        "informations_manquantes",
        "informations_non_exposees",
        "informations_fournies_par_analyste",
        "hypotheses_non_verifiees",
        "incoherences",
        "patterns_detectes",
        "verification_secondaire",
        "synthese",
        "validation_humaine_requise",
    ]

    STATUTS_AUTORISES = {
        "complet",
        "incomplet",
        "a_verifier",
    }

    NIVEAUX_AUTORISES = {
        "eleve",
        "moyen",
        "faible",
    }

    POSITIONS_AUTORISEES = {
        "favorable",
        "favorable_avec_conditions",
        "defavorable",
        "non_determinable",
    }

    TYPES_CHAT_AUTORISES = {
        "salutation",
        "reponse",
        "clarification",
        "refus",
    }

    def __init__(self):
        self.nom = "Emma IA"
        self.version = "2.1.2"

        self.stats = {
            "appels": 0,
            "erreurs": 0,
        }

        if not settings.deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY non trouvée dans .env"
            )

        self.client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

        self.system_prompt = self._charger_prompt()

        logger.info(
            "%s %s initialisée",
            self.nom,
            self.version,
        )

    def _charger_prompt(self) -> str:
        """
        Charge le prompt système depuis le dossier prompts.
        """

        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "prompts",
            "emma_system.txt",
        )

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()

            if not prompt.strip():
                raise ValueError(
                    "Le prompt emma_system.txt est vide"
                )

            return prompt

        except FileNotFoundError:
            logger.error(
                "Prompt Emma IA introuvable : %s",
                prompt_path,
            )

            return (
                "Tu es Emma IA, assistante de SecureFinance-RAG. "
                "Analyse uniquement les données fournies. "
                "N'invente aucune information. "
                "Ne modifie jamais les métriques officielles. "
                "Tu es un outil d'assistance et non un système "
                "de décision autonome."
            )

        except Exception:
            logger.exception(
                "Erreur lors du chargement du prompt Emma IA"
            )

            return (
                "Tu es Emma IA, assistante de SecureFinance-RAG. "
                "Analyse uniquement les données fournies. "
                "N'invente aucune information."
            )

    def _deplier_si_double_enveloppe(
        self,
        dossier_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Protection contre un payload déjà enveloppé.

        Si l'appelant envoie déjà une structure du type :

        {
            "donnees_dossier": {...},
            "metriques_officielles_calculees": {...}
        }

        au lieu d'un dossier plat, on déplie automatiquement pour éviter
        que les vraies données se retrouvent imbriquées deux niveaux
        trop profond.
        """

        if (
            "donnees_dossier" in dossier_data
            and isinstance(
                dossier_data["donnees_dossier"],
                dict,
            )
        ):
            logger.warning(
                "Payload deja enveloppe detecte "
                "(cle 'donnees_dossier' presente en entree) "
                "— depliage automatique effectue"
            )

            deplie = dict(
                dossier_data["donnees_dossier"]
            )

            metriques_deja_extraites = dossier_data.get(
                "metriques_officielles_calculees"
            )

            if metriques_deja_extraites:
                deplie[
                    "metriques_officielles_calculees"
                ] = metriques_deja_extraites

            champs_deja_extraits = dossier_data.get(
                "champs_obligatoires_pour_ce_produit"
            )

            if champs_deja_extraits:
                deplie[
                    "champs_obligatoires_pour_ce_produit"
                ] = champs_deja_extraits

            hypotheses_deja_extraites = dossier_data.get(
                "hypotheses_deja_ajoutees"
            )

            if hypotheses_deja_extraites:
                deplie[
                    "hypotheses_deja_ajoutees"
                ] = hypotheses_deja_extraites

            return deplie

        return dict(dossier_data)

    def _preparer_contexte(
        self,
        dossier_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Prépare le contexte transmis à Emma IA.

        Les champs de contexte ajoutés par l'application
        (métriques officielles, champs obligatoires et hypothèses
        déjà ajoutées par l'analyste) sont extraits avant le
        dépliage afin de supporter les deux formats de payload.
        """

        # ---------------------------------------------------------
        # Champs obligatoires
        # ---------------------------------------------------------

        champs_obligatoires = dossier_data.get(
            "champs_obligatoires_pour_ce_produit",
            None,
        )

        if not isinstance(champs_obligatoires, list):
            champs_obligatoires = []

        # ---------------------------------------------------------
        # Hypothèses déjà ajoutées
        #
        # IMPORTANT :
        # extraction AVANT le dépliage, exactement comme
        # champs_obligatoires_pour_ce_produit.
        # ---------------------------------------------------------

        hypotheses_deja_ajoutees = dossier_data.get(
            "hypotheses_deja_ajoutees",
            None,
        )

        if not isinstance(hypotheses_deja_ajoutees, list):
            hypotheses_deja_ajoutees = []

        # ---------------------------------------------------------
        # Dépliage du dossier
        # ---------------------------------------------------------

        donnees_dossier = self._deplier_si_double_enveloppe(
            dossier_data
        )

        # ---------------------------------------------------------
        # Métriques officielles
        # ---------------------------------------------------------

        metriques_officielles = donnees_dossier.pop(
            "metriques_officielles_calculees",
            None,
        )

        anciennes_metriques = donnees_dossier.pop(
            "metriques_systeme",
            None,
        )

        # ---------------------------------------------------------
        # Champs obligatoires éventuellement présents
        # après le dépliage
        # ---------------------------------------------------------

        if not champs_obligatoires:
            champs_depuis_deplie = donnees_dossier.pop(
                "champs_obligatoires_pour_ce_produit",
                None,
            )

            if isinstance(
                champs_depuis_deplie,
                list,
            ):
                champs_obligatoires = (
                    champs_depuis_deplie
                )
        else:
            # Même lorsqu'ils ont été trouvés à la racine,
            # on les retire du dossier métier.
            donnees_dossier.pop(
                "champs_obligatoires_pour_ce_produit",
                None,
            )

        # ---------------------------------------------------------
        # Hypothèses éventuellement présentes
        # après le dépliage
        # ---------------------------------------------------------

        if not hypotheses_deja_ajoutees:
            hyp_depuis_deplie = donnees_dossier.pop(
                "hypotheses_deja_ajoutees",
                None,
            )

            if isinstance(
                hyp_depuis_deplie,
                list,
            ):
                hypotheses_deja_ajoutees = (
                    hyp_depuis_deplie
                )
        else:
            # Même lorsqu'elles ont été trouvées à la racine,
            # on les retire du dossier métier.
            donnees_dossier.pop(
                "hypotheses_deja_ajoutees",
                None,
            )

        # ---------------------------------------------------------
        # Sécurisation des métriques
        # ---------------------------------------------------------

        if metriques_officielles is None:
            metriques_officielles = {}

        if not isinstance(
            metriques_officielles,
            dict,
        ):
            logger.warning(
                "metriques_officielles_calculees "
                "n'est pas un dictionnaire"
            )

            metriques_officielles = {}

        if (
            not metriques_officielles
            and isinstance(
                anciennes_metriques,
                dict,
            )
        ):
            metriques_officielles = anciennes_metriques

        # ---------------------------------------------------------
        # Contrôles de présence
        # ---------------------------------------------------------

        def present(champ: str) -> bool:
            return (
                champ in donnees_dossier
                and donnees_dossier[champ] is not None
            )

        controles = {
            "historique_credit_present": present(
                "historique_credit"
            ),
            "montant_demande_present": present(
                "montant_demande"
            ),
            "duree_demandee_present": present(
                "duree_demandee"
            ),
            "type_credit_present": present(
                "type_credit"
            ),
            "revenu_mensuel_present": (
                present("revenu_mensuel")
                or (
                    present("revenus")
                    and isinstance(
                        donnees_dossier.get("revenus"),
                        dict,
                    )
                    and donnees_dossier[
                        "revenus"
                    ].get(
                        "revenu_mensuel"
                    ) is not None
                )
            ),
            "dettes_presentes": present(
                "dettes"
            ),
            "metriques_officielles_presentes": bool(
                metriques_officielles
            ),
            "champs_obligatoires_presents": bool(
                champs_obligatoires
            ),
            "hypotheses_deja_ajoutees_presentes": bool(
                hypotheses_deja_ajoutees
            ),
        }

        if not any(controles.values()):
            logger.warning(
                "Aucune donnee significative detectee "
                "dans le dossier apres preparation du contexte "
                "— verifier le format du payload envoye "
                "a EmmaIA.analyser()"
            )

        return {
            "donnees_dossier": donnees_dossier,
            "metriques_officielles_calculees": (
                metriques_officielles
            ),
            "champs_obligatoires_pour_ce_produit": (
                champs_obligatoires
            ),
            "hypotheses_deja_ajoutees": (
                hypotheses_deja_ajoutees
            ),
            "controles_presence": controles,
        }

    def _valider_reponse(
        self,
        resultat: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Vérifie que la réponse d'Emma respecte le format attendu.

        Cette validation ne prend aucune décision métier.
        Elle sert uniquement à éviter qu'une réponse mal formée
        parte vers le reste de l'application.
        """

        if not isinstance(resultat, dict):
            raise ValueError(
                "La réponse Emma IA n'est pas un objet JSON"
            )

        for champ in self.CHAMPS_OBLIGATOIRES_SORTIE:
            if champ not in resultat:
                logger.warning(
                    "Champ manquant dans la réponse Emma IA : %s",
                    champ,
                )

        statut = resultat.get(
            "statut_dossier"
        )

        if (
            statut is not None
            and statut not in self.STATUTS_AUTORISES
        ):
            logger.warning(
                "Statut Emma IA invalide : %s",
                statut,
            )

            resultat["statut_dossier"] = (
                "a_verifier"
            )

        niveau = resultat.get(
            "niveau_confiance"
        )

        if (
            niveau is not None
            and niveau not in self.NIVEAUX_AUTORISES
        ):
            logger.warning(
                "Niveau de confiance Emma IA invalide : %s",
                niveau,
            )

            resultat["niveau_confiance"] = (
                "faible"
            )

        synthese = resultat.get(
            "synthese"
        )

        if isinstance(synthese, dict):
            position = synthese.get(
                "position"
            )

            if (
                position is not None
                and position not in self.POSITIONS_AUTORISEES
            ):
                logger.warning(
                    "Position Emma IA invalide : %s",
                    position,
                )

                synthese["position"] = (
                    "non_determinable"
                )

        return resultat

    def analyser(
        self,
        dossier_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analyse complète d'un dossier anonymisé.

        dossier_data peut être un dossier plat ou une enveloppe
        contenant donnees_dossier, metriques officielles,
        champs obligatoires et hypothèses déjà ajoutées.

        Les hypothèses fournies par l'analyste sont transmises
        séparément au modèle et doivent apparaître dans
        hypotheses_non_verifiees.
        """

        try:
            if not isinstance(
                dossier_data,
                dict,
            ):
                raise TypeError(
                    "dossier_data doit être un dictionnaire"
                )

            contexte = self._preparer_contexte(
                dossier_data
            )

            instruction = (
                "Analyse le dossier suivant conformément "
                "STRICTEMENT aux règles de ton prompt système.\n\n"

                "IMPORTANT :\n\n"

                "1. Utilise uniquement les données présentes "
                "dans donnees_dossier.\n\n"

                "2. Une donnée absente ne doit jamais être "
                "présentée comme présente.\n\n"

                "3. Les seules métriques officielles sont "
                "celles présentes dans "
                "metriques_officielles_calculees.\n\n"

                "4. Ne recalcule jamais une métrique officielle.\n\n"

                "5. Ne modifie jamais une métrique officielle.\n\n"

                "6. Ne transforme jamais une donnée brute en "
                "métrique officielle.\n\n"

                "7. Si une métrique officielle nécessaire "
                "est absente, signale-la dans "
                "informations_manquantes.\n\n"

                "8. Un calcul indicatif doit rester dans "
                "verification_secondaire et être clairement "
                "identifié comme non officiel.\n\n"

                "9. Si historique_credit est présent, il doit "
                "être repris dans "
                "informations_verifiees.historique_credit "
                "et contextualisé dans patterns_detectes.\n\n"

                "10. Si montant_demande, duree_demandee ou "
                "type_credit sont présents, ils doivent "
                "apparaître dans informations_verifiees.demande.\n\n"

                "11. Ne mélange jamais plusieurs dossiers.\n\n"

                "12. N'invente aucune information.\n\n"

                "13. Ne déduis aucune caractéristique sensible.\n\n"

                "14. Ne crée aucun seuil ou aucune règle métier "
                "qui n'est pas fournie.\n\n"

                "15. Ne prends jamais une décision de crédit "
                "automatique.\n\n"

                "16. La position doit être exactement l'une de : "
                "favorable, favorable_avec_conditions, "
                "defavorable, non_determinable.\n\n"

                "17. Le champ de sortie pour les métriques "
                "officielles se nomme metriques_officielles.\n\n"

                "18. Retourne UNIQUEMENT le JSON demandé par "
                "le prompt système.\n\n"

                "19. Si le contexte contient "
                "hypotheses_deja_ajoutees non vide, chacune de "
                "ces entrées doit apparaître dans "
                "hypotheses_non_verifiees de ta sortie, avec "
                "source 'Analyste', jamais fusionnée "
                "silencieusement aux données vérifiées.\n\n"

                "DONNEES A ANALYSER :\n"
                f"{json.dumps(contexte, ensure_ascii=False, indent=2)}"
            )

            response = self.client.chat.completions.create(
                model=settings.deepseek_model,
                messages=[
                    {
                        "role": "system",
                        "content": self.system_prompt,
                    },
                    {
                        "role": "user",
                        "content": instruction,
                    },
                ],
                response_format={
                    "type": "json_object"
                },
                temperature=0.1,
            )

            self.stats["appels"] += 1

            contenu = (
                response.choices[0]
                .message.content
            )

            if not contenu:
                raise ValueError(
                    "Réponse vide du modèle"
                )

            try:
                resultat = json.loads(
                    contenu.strip()
                )

            except json.JSONDecodeError as exc:
                logger.error(
                    "JSON invalide retourné par Emma IA : %s",
                    exc,
                )

                raise ValueError(
                    "Le modèle a retourné un JSON invalide"
                ) from exc

            return self._valider_reponse(
                resultat
            )

        except Exception as erreur:
            self.stats["erreurs"] += 1

            logger.exception(
                "Erreur pendant l'analyse Emma IA"
            )

            return self._reponse_erreur(
                erreur
            )

    def _reponse_erreur(
        self,
        erreur: Exception,
    ) -> Dict[str, Any]:
        """
        Réponse de secours lorsqu'une erreur technique survient.

        Emma ne fabrique aucune métrique et ne donne aucune
        position favorable ou défavorable dans ce cas.
        """

        message = str(erreur)

        if len(message) > 200:
            message = message[:200]

        return {
            "statut_dossier": "a_verifier",
            "niveau_confiance": "faible",
            "informations_verifiees": {
                "demandeur": {},
                "demande": {},
                "revenus": {},
                "dettes": [],
                "historique_credit": {},
            },
            "metriques_officielles": {},
            "informations_manquantes": [],
            "informations_non_exposees": [],
            "informations_fournies_par_analyste": [],
            "hypotheses_non_verifiees": [],
            "incoherences": [],
            "patterns_detectes": [],
            "verification_secondaire": {},
            "synthese": {
                "position": "non_determinable",
                "texte": (
                    "L'analyse automatique n'a pas pu être "
                    "terminée. Une vérification humaine est requise."
                ),
                "base_sur": [],
            },
            "validation_humaine_requise": [
                "Relancer l'analyse Emma IA.",
                "Vérifier les données du dossier.",
                "Ne prendre aucune décision automatique "
                "sur la base de cette erreur.",
            ],
            "erreur_technique": message,
        }

    def _valider_envelope_chat(
        self,
        resultat: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Valide et normalise l'enveloppe JSON du chat.

        Le chat contextualisé doit toujours retourner un objet
        conforme au format défini dans la section 9 du prompt système.
        """

        if not isinstance(
            resultat,
            dict,
        ):
            raise ValueError(
                "La réponse chat d'Emma IA n'est pas un objet JSON"
            )

        if (
            resultat.get("type")
            not in self.TYPES_CHAT_AUTORISES
        ):
            logger.warning(
                "Type de chat invalide : %s",
                resultat.get("type"),
            )

            resultat["type"] = "reponse"

        if not resultat.get("message"):
            resultat["message"] = (
                "Je n'ai pas pu formuler de réponse claire. "
                "Pouvez-vous reformuler votre question ?"
            )

        position = resultat.get(
            "position"
        )

        if (
            position is not None
            and position not in self.POSITIONS_AUTORISEES
        ):
            logger.warning(
                "Position invalide dans le chat : %s",
                position,
            )

            resultat["position"] = None

        niveau = resultat.get(
            "niveau_confiance"
        )

        if (
            niveau is not None
            and niveau not in self.NIVEAUX_AUTORISES
        ):
            logger.warning(
                "Niveau de confiance invalide dans le chat : %s",
                niveau,
            )

            resultat["niveau_confiance"] = None

        if not isinstance(
            resultat.get("elements_favorables"),
            list,
        ):
            resultat["elements_favorables"] = []

        if not isinstance(
            resultat.get("points_attention"),
            list,
        ):
            resultat["points_attention"] = []

        if not isinstance(
            resultat.get("validation_humaine_requise"),
            list,
        ):
            resultat["validation_humaine_requise"] = []

        return resultat

    def chat(
        self,
        message: str,
    ) -> str:
        """
        Chat conversationnel avec l'analyste.

        Le chat simple répond en texte.
        Le chat contextualisé utilise une enveloppe JSON structurée.
        """

        if not message or not message.strip():
            return (
                "Je n'ai reçu aucun message. "
                "Pouvez-vous préciser votre question ?"
            )

        chat_prompt = (
            self.system_prompt
            + """

CONTEXTE ACTUEL : CHAT AVEC L'ANALYSTE

Tu échanges actuellement avec un analyste humain.

Réponds de manière naturelle, professionnelle,
claire et collaborative.

Règles supplémentaires pour le chat :

1. N'invente aucune donnée.
2. Ne prétends jamais avoir consulté un document
   qui n'est pas présent dans la conversation.
3. Utilise uniquement les informations disponibles.
4. Si une information manque, indique-le clairement.
5. Ne modifie jamais une métrique officielle.
6. Ne prends jamais une décision de crédit à la place
   de l'analyste.
7. Ne déduis jamais de caractéristique sensible.
8. Si l'analyste demande explicitement une analyse
   complète au format JSON, respecte le format JSON
   défini dans le prompt système.
9. Sinon, réponds normalement en texte.
10. Lorsque c'est pertinent, propose une prochaine
    étape ou pose une question permettant à l'analyste
    de poursuivre son analyse.
"""
        )

        try:
            response = self.client.chat.completions.create(
                model=settings.deepseek_model,
                messages=[
                    {
                        "role": "system",
                        "content": chat_prompt,
                    },
                    {
                        "role": "user",
                        "content": message.strip(),
                    },
                ],
                temperature=0.7,
            )

            self.stats["appels"] += 1

            contenu = (
                response.choices[0]
                .message.content
            )

            if not contenu:
                raise ValueError(
                    "Réponse vide du modèle"
                )

            return contenu.strip()

        except Exception:
            self.stats["erreurs"] += 1

            logger.exception(
                "Erreur pendant le chat Emma IA"
            )

            return (
                "Je ne peux pas traiter cette demande "
                "pour le moment. Veuillez réessayer."
            )

    def chat_contextualise(
        self,
        message: str,
        dossier_context: Dict[str, Any],
        historique_messages: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """
        Chat avec mémoire du dossier ET de la conversation en cours.

        Retourne TOUJOURS une enveloppe JSON structurée :

        {
            "type": "...",
            "message": "...",
            "position": "...",
            "niveau_confiance": "...",
            "elements_favorables": [...],
            "points_attention": [...],
            "validation_humaine_requise": [...]
        }

        Jamais de texte libre.
        """

        if not message or not message.strip():
            return {
                "type": "clarification",
                "message": (
                    "Je n'ai reçu aucun message. "
                    "Pouvez-vous préciser votre question ?"
                ),
                "position": None,
                "niveau_confiance": None,
                "elements_favorables": [],
                "points_attention": [],
                "validation_humaine_requise": [],
            }

        dossier_resume = json.dumps(
            dossier_context,
            ensure_ascii=False,
            indent=2,
        )

        chat_prompt = (
            self.system_prompt
            + f"""

CONTEXTE ACTUEL : CHAT AVEC L'ANALYSTE

Tu échanges avec un analyste au sujet du dossier suivant.
Utilise-le comme source de vérité, jamais une valeur mentionnée
plus tôt dans la conversation si elle diffère de ce qui suit.

DOSSIER ACTUEL :
{dossier_resume}

Rappel impératif :

Réponds STRICTEMENT selon le format JSON défini dans la
section 9 (CONTEXTE A — CHAT) du prompt système.

Tu dois retourner uniquement un objet JSON.

Jamais de texte hors de cette structure JSON, même pour
un simple "bonjour".

Le champ "type" doit obligatoirement être l'une des valeurs suivantes :

- "salutation"
- "reponse"
- "clarification"
- "refus"

Le champ "message" doit toujours contenir une réponse textuelle.

Le champ "position" doit être null ou l'une des valeurs suivantes :

- "favorable"
- "favorable_avec_conditions"
- "defavorable"
- "non_determinable"

Le champ "niveau_confiance" doit être null ou l'une des valeurs suivantes :

- "eleve"
- "moyen"
- "faible"

Les champs suivants doivent toujours être des tableaux :

- "elements_favorables"
- "points_attention"
- "validation_humaine_requise"

N'invente aucune donnée.

Ne modifie jamais une métrique officielle.

Ne prends jamais une décision de crédit autonome.

Si une information manque, indique-le clairement.

Si une validation humaine est nécessaire, indique-la dans
validation_humaine_requise.
"""
        )

        messages = [
            {
                "role": "system",
                "content": chat_prompt,
            }
        ]

        # Protection contre un historique mal formé.
        for historique in historique_messages:
            if not isinstance(
                historique,
                dict,
            ):
                continue

            role = historique.get(
                "role"
            )

            content = historique.get(
                "content"
            )

            if role not in {
                "user",
                "assistant",
            }:
                continue

            if not isinstance(
                content,
                str,
            ):
                continue

            messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": message.strip(),
            }
        )

        try:
            response = self.client.chat.completions.create(
                model=settings.deepseek_model,
                messages=messages,
                response_format={
                    "type": "json_object"
                },
                temperature=0.4,
            )

            self.stats["appels"] += 1

            contenu = (
                response.choices[0]
                .message.content
            )

            if not contenu:
                raise ValueError(
                    "Réponse vide du modèle"
                )

            try:
                resultat = json.loads(
                    contenu.strip()
                )

            except json.JSONDecodeError as exc:
                logger.error(
                    "JSON invalide retourné par Emma IA "
                    "pendant le chat contextualisé : %s",
                    exc,
                )

                raise ValueError(
                    "Le modèle a retourné un JSON de chat invalide"
                ) from exc

            return self._valider_envelope_chat(
                resultat
            )

        except Exception:
            self.stats["erreurs"] += 1

            logger.exception(
                "Erreur pendant le chat contextualisé Emma IA"
            )

            return {
                "type": "refus",
                "message": (
                    "Je ne peux pas traiter cette demande "
                    "pour le moment. Veuillez réessayer."
                ),
                "position": None,
                "niveau_confiance": None,
                "elements_favorables": [],
                "points_attention": [],
                "validation_humaine_requise": [
                    "Réessayer la demande.",
                    "Effectuer une vérification humaine "
                    "si l'information est nécessaire à la décision.",
                ],
            }

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "nom": self.nom,
            "version": self.version,
            "modele": settings.deepseek_model,
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            "nom": self.nom,
            "version": self.version,
            "stats": dict(self.stats),
        }
