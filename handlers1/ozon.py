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

from db.base import OzonProduct as OzonProductModel, User
# from .base import start


ozon_router = Router()


@ozon_router.callback_query(F.data == 'add_product')
async def add_product(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
    await state.set_state(OzonProduct.product)
    data = await state.get_data()

    msg: types.Message = data.get('msg')
    _text = 'Отправьте ссылку на товар'

    _kb = create_or_add_cancel_btn()

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await callback.message.answer(text=_text,
                             reply_markup=_kb.as_markup())
        

@ozon_router.message(OzonProduct.product)
async def proccess_product(message: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot):
    data = await state.get_data()

    msg: types.Message = data.get('msg')

    _kb = create_done_kb(marker='ozon_product')

    _kb = create_or_add_cancel_btn(_kb)

    ozon_link = message.text

    await state.update_data(ozon_link=ozon_link)

    _prefix = 'product/'

    _idx = ozon_link.rfind('product/')

    ozon_product_id = ozon_link[(_idx + len(_prefix)):]

    await state.update_data(ozon_product_id=ozon_product_id)

    try:
        async with aiohttp.ClientSession() as aiosession:
            # _url = f"http://5.61.53.235:1441/product/{message.text}"
            _url = f"http://172.18.0.4:8080/product/{ozon_product_id}"

            response = await aiosession.get(url=_url)

            res = await response.text()

            w = re.findall(r'\"cardPrice.*currency?', res)
            print(w)

            w = w[0].split(',')[:3]

            _d = {
                'price': None,
                'originalPrice': None,
                'cardPrice': None,
            }

            for k in _d:
                if not all(v for v in _d.values()):
                    for q in w:
                        if q.find(k) != -1:
                            name, price = q.split(':')
                            price = price.replace('\\', '').replace('"', '')
                            price = float(''.join(price.split()[:-1]))
                            print(price)
                            _d[k] = price
                            break
                else:
                    break

            print(_d)

            await state.update_data(ozon_basic_price=_d.get('price', 0))
            await state.update_data(ozon_actual_price=_d.get('cardPrice', 0))

            price_text = '|'.join(str(v) for v in _d.items())

        _text = f'Ваш продукт\n{message.text}\nЦена продукта: {price_text}'

        await state.update_data(ozon_product=message.text)

        if msg:
            await bot.edit_message_text(text=_text,
                                        chat_id=message.chat.id,
                                        message_id=msg.message_id,
                                        reply_markup=_kb.as_markup())
        else:
            await bot.send_message(chat_id=message.chat.id,
                                text=_text,
                                reply_markup=_kb.as_markup())
            
        await message.delete()
    except Exception as ex:
        pass
        

@ozon_router.callback_query(F.data == 'list_product')
async def list_product(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        bot: Bot):
    data = await state.get_data()

    _kb = create_or_add_cancel_btn()

    msg = data.get('msg')

    ozon_product = data.get('ozon_product')

    if ozon_product:
        _text = f'Ваш Ozon товар:\n{ozon_product}'
        if msg:
            await bot.edit_message_text(chat_id=callback.message.chat.id,
                                        text=_text,
                                        message_id=msg.message_id,
                                        reply_markup=_kb.as_markup())
        else:
            await bot.send_message(chat_id=callback.message.chat.id,
                                   text=_text,
                                   reply_markup=_kb.as_markup())
    else:
        await callback.answer(text='Нет добавленных Ozon товаров',
                              show_alert=True)


@ozon_router.message(F.text == 'test_ozon_pr')
async def test_db_ozon(message: types.Message,
                       session: AsyncSession):
    user_id = message.from_user.id

    query = (
        select(OzonProductModel)\
        .join(User,
              OzonProductModel.user_id == User.id)\
        .where(User.id == user_id)
    )

    ozon_product = await session.execute(query)

    ozon_product = ozon_product.scalar_one_or_none()

    print('ozon product', ozon_product)

    if ozon_product:
        await message.answer(f'привет {ozon_product.user_id}, {ozon_product.user}, {ozon_product.link}, {ozon_product.actual_price}')