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
    # scheduler.print_jobs()
    
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


@main_router.callback_query(F.data.startswith('bot'))
async def redirect_to_(callback: types.CallbackQuery,
                        state: FSMContext,
                        bot: Bot,
                        marker: str = None):
    if not marker:
        marker = callback.data.split('_')[-1]

    await state.update_data(action=marker)

    data = await state.get_data()
    msg = data.get('msg')

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
                            bot: Bot,):
    # await start(callback,
    #             state,
    #             bot)
    data = await state.get_data()

    action = data.get('action')

    await redirect_to_(callback,
                       state,
                       bot,
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
                                        callback_data)
    
    await callback.answer(text=_text,
                          show_alert=True)
    
    await redirect_to_(callback,
                       state,
                       bot,
                       marker=action)
    
    # await callback.answer(text='Пункт выдачи добавлен.',
    #                       show_alert=True)
    # await start(callback,
    #             state,
    #             session,
    #             bot,
    #             scheduler)