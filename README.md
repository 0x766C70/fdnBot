# fdnBot - FDN-Expert

Agent conversationnel expert en informatique et spécialiste de **FDN (French Data Network,
fdn.fr)**, construit avec LangChain 1.x et le modèle Mistral. Sa recherche web est
strictement limitée aux sites `*.fdn.fr`.

Détectez bien la structure du projet :

```
fdnBot/
├── fdn_bot/              # Cœur de l'agent
│   ├── agent.py          # create_agent (LangChain 1.x) + ChatMistralAI
│   ├── prompts.py        # Prompt système : expert IT / FDN
│   ├── tools.py          # search_on_fdn (Tavily, include_domains=fdn.fr)
│   │                     # + read_fdn_page (lecture, garde-fou *.fdn.fr)
│   └── __main__.py       # CLI locale interactive
├── api/
│   └── chat.py           # App FastAPI : entrypoint unique Vercel
│                          # GET / (UI) + GET/POST /api/chat
├── public/
│   └── index.html        # Mini interface de chat (statique)
├── requirements.txt      # Dépendances pour le runtime Vercel (Python 3.12)
├── vercel.json           # maxDuration 60s (fonction unique api/chat.py)
├── pyproject.toml        # Dépendances uv pour le développement local
└── .env.example
```

## Fonctionnement de l'agent

L'agent est assemblé avec `create_agent` (API LangChain 1.x) autour de deux outils :

1. **`search_on_fdn`** : recherche web Tavily avec `include_domains=["fdn.fr"]`,
   donc restreinte à `fdn.fr` et ses sous-domaines (`*.fdn.fr`).
2. **`read_fdn_page`** : lit le texte d'une page web, mais **refuse toute URL
   dont l'hôte n'est pas `fdn.fr` ou `*.fdn.fr`** (et bloque aussi les
   redirections sortantes du domaine). Double garde-fou : même si le modèle
   tente une URL externe, la lecture est refusée.

Le prompt système impose de sourcer toute réponse sur FDN vers fdn.fr et de
citer les URLs consultées.

## Développement local

```bash
uv sync                        # deps de production + dev (tests, uvicorn)
cp .env.example .env          # renseigner MISTRAL_API_KEY et TAVILY_API_KEY
uv run python -m fdn_bot       # CLI interactive
uv run uvicorn api.chat:app    # API FastAPI locale sur http://127.0.0.1:8000
uv run pytest tests/ -q        # tests
```

Les dépendances du cours LangChain sont dans le group `course` (non installé
par défaut, ni sur Vercel qui n'installe que `[project] dependencies`) :
`uv sync --group course`.

## Appel de l'API en direct

```bash
curl -X POST https://<votre-deploiement>.vercel.app/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Comment adhérer à FDN ?"}]}'
```

Réponse : `{"answer": "..."}`. Un `GET /api/chat` sert de health check.

## Déploiement Vercel

Le projet est déployé comme application Python mono-entrypoint (pattern
officiel Vercel) : l'app FastAPI `app` de `api/chat.py` reçoit toutes les
requêtes. L'entrypoint est déclaré dans `pyproject.toml` :

```toml
[tool.vercel]
entrypoint = "api.chat:app"
```

1. Pousser ce repository sur GitHub.
2. Sur Vercel : **Add New Project** -> importer le repo (Root Directory : racine).
3. Dans **Settings -> Environment Variables**, ajouter :
   - `MISTRAL_API_KEY` (requis)
   - `TAVILY_API_KEY` (requis)
   - `MISTRAL_MODEL` (optionnel, défaut `mistral-large-latest`).
4. Déployer. Le frontend statique `public/index.html` est servi sur `/`,
   l'agent répond sur `/api/chat`.

Note : `.env` est ignoré par git ; il n'est jamais poussé ni déployé.
