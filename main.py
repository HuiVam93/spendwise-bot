import os
import multiprocessing
import asyncio
from spendwise_bot import main as bot_main, init_db
from api import app as fastapi_app
import uvicorn

def run_api():
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    init_db()
    
    # API запускаем в отдельном процессе
    api_process = multiprocessing.Process(target=run_api)
    api_process.start()
    
    # Бота запускаем в основном процессе
    asyncio.run(bot_main())
