import asyncio

import redis

import uvicorn

import redis.asyncio
import redis.asyncio.client
from uvicorn import Config, Server

from pyrogram import Client

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from starlette.middleware.cors import CORSMiddleware

from fastapi import FastAPI, APIRouter

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db.base import engine, session, Base

from middlewares.db import DbSessionMiddleware

from config import (TOKEN,
                    db_url,
                    PUBLIC_URL,
                    API_ID,
                    API_HASH,
                    REDIS_HOST,
                    REDIS_PASSWORD)
# from handlers import main_router

from handlers1.base import main_router
from handlers1.ozon import ozon_router
from handlers1.wb import wb_router

#TG BOT
bot = Bot(TOKEN, parse_mode="HTML")

# #####
# # api_client = Client('my_account',
# #                     api_id=API_ID,
# #                     api_hash=API_HASH)
# #####

dp = Dispatcher()
dp.include_router(ozon_router)
dp.include_router(wb_router)
dp.include_router(main_router)

scheduler = AsyncIOScheduler()

scheduler.start()

# #Add session and database connection in handlers 
dp.update.middleware(DbSessionMiddleware(session_pool=session,
                                         scheduler=scheduler))

# #Initialize web server
app = FastAPI(docs_url='/docs_send')
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
event_loop = asyncio.get_event_loop()
config = Config(app=app,
                loop=event_loop,
                host='0.0.0.0',
                port=8001)
server = Server(config)


# fast_api_router = APIRouter(prefix='/bot_api')
# # app.include_router(fast_api_router)

# #For set webhook
WEBHOOK_PATH = f'/webhook_'



async def init_db():
    async with engine.begin() as conn:
        # Создаем таблицы
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

# #Set webhook and create database on start
@app.on_event('startup')
async def on_startup():
    await bot.delete_webhook()
    await bot.set_webhook(f"{PUBLIC_URL}{WEBHOOK_PATH}",
                          allowed_updates=['message', 'callback_query'])
                        #   drop_pending_updates=True,
    
    await init_db()
    
#     # Base.prepare(engine, reflect=True)


# #Endpoint for checking
# @app.get(WEBHOOK_PATH)
# async def any():
#     return {'status': 'ok'}


# #Endpoint for incoming updates
@app.post(WEBHOOK_PATH)
async def bot_webhook(update: dict):
    tg_update = types.Update(**update)
    await dp.feed_update(bot=bot, update=tg_update)


# @app.get('/send_to_tg_group')
# async def send_to_tg_group(user_id: int,
#                            order_id: int,
#                            marker: str):
#     await test_send(user_id=user_id,
#                     order_id=order_id,
#                     marker=marker,
#                     session=session(),
#                     bot=bot)
#Endpoint for mass send message
# @app.get('/send_mass_message')
# async def send_mass_message_for_all_users(name_send: str):
#     await send_mass_message(bot=bot,
#                             session=session(),
#                             name_send=name_send)
    

# app.include_router(fast_api_router)
# fast_api_router = APIRouter()

# @fast_api_router.get('/test')
# async def test_api():
#     Guest = Base.classes.general_models_guest

#     # with session() as conn:
#     #     conn: Session
#     #     conn.query(Guest)
#     await bot.send_message('686339126', 'what`s up')
    
# app = FastAPI()

# bot = Bot(TOKEN, parse_mode="HTML")

###

# fast_api_router = APIRouter()

# @fast_api_router.get('/test')
# async def test_api():
#     Guest = Base.classes.general_models_guest

#     # with session() as conn:
#     #     conn: Session
#     #     conn.query(Guest)
#     await send_mass_message(bot=bot,
#                             session=session())
    # await bot.send_message('686339126', 'what`s up')

# app.include_router(fast_api_router)
    ###


# async def main():
#     bot = Bot(TOKEN, parse_mode="HTML")
    # w = await bot.get_my_commands()
    # print(w)
    # await bot.set_my_commands([
    #     types.BotCommand(command='send',description='send mass message'),
    # ])
    # w = await bot.get_my_commands()
    # print(w)


    # api_client = Client('my_account',
    #                     api_id=API_ID,
    #                     api_hash=API_HASH)



    # dp = Dispatcher()
    # dp.include_router(main_router)
    # dp.update.middleware(DbSessionMiddleware(session_pool=session))

    # engine = create_engine(db_url,
    #                        echo=True)

    # Base.prepare(engine, reflect=True)
    

    # await bot.delete_webhook(drop_pending_updates=True)
    # await dp.start_polling(bot)
    # await event_loop.run_until_complete(server.serve())
    # uvicorn.run('main:app', host='0.0.0.0', port=8001)


# if __name__ == '__main__':
#     asyncio.run(main())
if __name__ == '__main__':
    event_loop.run_until_complete(server.serve())