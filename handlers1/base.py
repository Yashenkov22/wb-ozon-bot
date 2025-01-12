import os
import json
import re

import aiohttp

import pytz

from datetime import datetime

from aiogram import Router, types, Bot, F
from aiogram.types import BufferedInputFile, URLInputFile
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from sqlalchemy.orm import Session, joinedload, sessionmaker
from sqlalchemy import insert, select, update, or_

from sqlalchemy.ext.asyncio import AsyncSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BEARER_TOKEN, FEEDBACK_REASON_PREFIX

from keyboards import (create_start_kb,
                       create_or_add_cancel_btn,
                       create_done_kb,
                       create_wb_start_kb,
                       add_back_btn,
                       create_bot_start_kb)

from states import SwiftSepaStates, ProductStates, OzonProduct

from utils.handlers import save_data_to_storage, check_user
from utils.scheduler import test_scheduler

from db.base import OzonProduct as OzonProductModel, User, Base


main_router = Router()

start_text = '💱<b>Добро пожаловать в MoneySwap!</b>\n\nНаш бот поможет найти лучшую сделку под вашу задачу 💸\n\n👉🏻 <b>Чтобы начать поиск</b>, выберите категорию “безналичные”, “наличные” или “Swift/Sepa” и нажмите на нужную кнопку ниже.\n\nЕсли есть какие-то вопросы, обращайтесь <a href="https://t.me/MoneySwap_support">Support</a> или <a href="https://t.me/moneyswap_admin">Admin</a>. Мы всегда готовы вам помочь!'

moscow_tz = pytz.timezone('Europe/Moscow')


@main_router.message(Command('start'))
async def start(message: types.Message | types.CallbackQuery,
                state: FSMContext,
                session: AsyncSession,
                bot: Bot,
                scheduler: AsyncIOScheduler):
    
    await check_user(message,
                     session)
    
    # logger.info('hi')
    # print(scheduler)
    # print(type(scheduler))
    scheduler.print_jobs()

    _product_name = 'wb'

    _product_id = 'test_product_id'

    job_name = f'{message.from_user.id}_{_product_name}_{_product_id}'

    _job = scheduler.add_job(test_scheduler,
                             'cron',
                             second=30,
                             args=(message.from_user.id, ),
                             name=job_name)

    scheduler.print_jobs()
    
    await state.update_data(action=None)

    if isinstance(message, types.CallbackQuery):
        message = message.message

    _kb = create_start_kb()
    msg = await bot.send_message(text='Привет.\nЭто тестовые WB и OZON боты.',
                                 chat_id=message.chat.id,
                                reply_markup=_kb.as_markup())
    
    await state.update_data(msg=msg)
    try:
        await message.delete()
    except Exception as ex:
        print(ex)


@main_router.message(Command('test_ozon_pr'))
async def test_db_ozon(message: types.Message,
                       state: FSMContext,
                       session: AsyncSession,
                       bot: Bot):
    user_id = message.from_user.id

    query = (
        select(
            OzonProductModel.link,
            OzonProductModel.actual_price,
            OzonProductModel.basic_price,
            OzonProductModel.time_create,
            OzonProductModel.user_id)\
        .join(User,
              OzonProductModel.user_id == User.tg_id)\
        .where(User.tg_id == user_id)
    )
    # async with session as session:
    ozon_product = await session.execute(query)

    ozon_product = ozon_product.fetchall()

    ozon_product = ozon_product[0]

    link, actual_price, basic_price, time_create, _user_id = ozon_product

    # ozon_product = ozon_product[0]

    # print('ozon product', ozon_product.user_id, ozon_product.user, ozon_product.link)

    if ozon_product:
        await message.answer(f'Привет {_user_id}\nТвой товар\n{link}\nОсновная цена: {basic_price}\nАктуальная цена: {actual_price}\nДата создания отслеживания: {time_create}')
    else:
        await message.answer('не получилось')


@main_router.callback_query(F.data.startswith('bot'))
async def redirect_to_(callback: types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler,
                        marker: str = None):
    scheduler.print_jobs()

    if not marker:
        marker = callback.data.split('_')[-1]

    await state.update_data(action=marker)

    data = await state.get_data()
    msg = data.get('msg')


    # JobModel = Base.classes.apscheduler_jobs

    print(Base)
    print(Base.metadata.__dir__())
###

    # query = (
    #     select(JobModel.name,
    #            JobModel.id)
    # )

    # res = await session.execute(query)
    # res = res.fetchall()

    # for r in res:
    #     print(r._data)
###



    _text = f'{marker.upper()} бот\nВыберите действие'

    _kb = create_bot_start_kb(marker=marker)

    _kb = add_back_btn(_kb)

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=callback.message.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await bot.send_message(chat_id=callback.message.chat.id,
                               text=_text,
                               reply_markup=_kb.as_markup())


@main_router.callback_query(F.data == 'cancel')
async def callback_cancel(callback: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    # await start(callback,
    #             state,
    #             bot)
    data = await state.get_data()

    action = data.get('action')

    await redirect_to_(callback,
                       state,
                       session,
                       bot,
                       scheduler,
                       marker=action)
    

@main_router.callback_query(F.data == 'to_main')
async def callback_cancel(callback: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    # callback_data = callback.data.split('_')[-1]

    # await redirect_to_(callback,
    #               state,
    #               bot,
    #               marker='wb')
    await start(callback,
                state,
                session,
                bot,
                scheduler)
    

@main_router.callback_query(F.data.startswith('done'))
async def callback_done(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler):
    data = await state.get_data()

    action = data.get('action')
    callback_data = callback.data.split('__')[-1]

    _text = await save_data_to_storage(callback,
                                        state,
                                        session,
                                        bot,
                                        scheduler,
                                        callback_data)
    
    await callback.answer(text=_text,
                          show_alert=True)
    
    await redirect_to_(callback,
                       state,
                       session,
                       bot,
                       scheduler,
                       marker=action)
    
    # await callback.answer(text='Пункт выдачи добавлен.',
    #                       show_alert=True)
    # await start(callback,
    #             state,
    #             session,
    #             bot,
    #             scheduler)

@main_router.message()
async def any_input(message: types.Message):
    await message.answer(text=message.text)