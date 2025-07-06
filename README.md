# Status Deck 

Status Deck is a  simple **API health monitoring platform** using FastAPI, Prisma, WebSockets, and Redis to track, alert, and display service statuses in real-time.


##  Local Development



Install dependencies:



```bash

pip install -r requirements.txt

```



---



Run the development environment:



```bash

./scripts/dev_run.sh

```



This will:



✅ Generate the Prisma client

✅ Start the FastAPI server (`uvicorn`) on `http://127.0.0.1:8000`

✅ Start the WebSocket broadcaster on `ws://127.0.0.1:8001`

✅ Start the Auto Incident Monitor

✅ Display ****live logs for all processes in your terminal****



---



Stop using:



```bash

Ctrl + C

```



to cleanly terminate all services.



---



###  Clear Cache



To fully clear Redis and local Prisma caches, use:



```bash

./scripts/full_clean.sh

```



---



When you update `prisma/schema.prisma`, regenerate the Prisma client by running:



```bash

python -m prisma generate

```



or simply rerun:



```bash

./scripts/dev_run.sh

```
