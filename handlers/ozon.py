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
from sqlalchemy import and_, insert, select, update, or_

from sqlalchemy.ext.asyncio import AsyncSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BEARER_TOKEN, FEEDBACK_REASON_PREFIX

from keyboards import (create_remove_kb, create_start_kb,
                       create_or_add_cancel_btn,
                       create_done_kb,
                       create_wb_start_kb,
                       add_back_btn,
                       create_bot_start_kb)

from states import SwiftSepaStates, ProductStates, OzonProduct
from utils.handlers import clear_state_and_redirect_to_start, save_data_to_storage, check_user, show_item

from db.base import OzonProduct as OzonProductModel, User, UserJob
# from .base import start


ozon_router = Router()


@ozon_router.callback_query(F.data == 'add_product')
async def add_product(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot):
    # query = (
    #     select(
    #         OzonProductModel.id
    #     )\
    #     .join(User,
    #           OzonProductModel.user_id == User.tg_id)\
    #     .where(User.tg_id == callback.from_user.id)
    # )
    # async with session as session:
    #     res = await session.execute(query)

    #     check_product_by_user = res.scalar_one_or_none()

    # if check_product_by_user:
    #     await callback.answer(text='Продукт уже добален',
    #                           show_alert=True)
    #     return

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
    
    await callback.answer()
        

@ozon_router.message(OzonProduct.product)
async def proccess_product(message: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot):
    ozon_link = message.text.strip()
    
    if ozon_link == '/start':
        await clear_state_and_redirect_to_start(message,
                                                state,
                                                bot)
        await message.delete()
        return

    data = await state.get_data()

    msg: types.Message = data.get('msg')

    query = (
        select(
            OzonProductModel.id
        )\
        .join(User,
            OzonProductModel.user_id == User.tg_id)\
        .where(
            and_(
                User.tg_id == message.from_user.id,
                OzonProductModel.link == ozon_link,
            )
        )
    )
    async with session as session:
        res = await session.execute(query)

        check_product_by_user = res.scalar_one_or_none()

    if check_product_by_user:
        _kb = create_or_add_cancel_btn()
        await msg.edit_text(text='Продукт уже добален',
                            reply_markup=_kb.as_markup())
        await message.delete()
        return

    # _kb = create_done_kb(marker='ozon_product')

    _kb = create_or_add_cancel_btn()


    await state.update_data(ozon_link=ozon_link)

    if ozon_link.startswith('https://ozon.ru/t/'):
        _idx = ozon_link.find('/t/')
        print(_idx)
        _prefix = '/t/'
        ozon_product_id = 'croppedLink|' + ozon_link[_idx+len(_prefix):]
        print(ozon_product_id)
    else:
        _prefix = 'product/'

        _idx = ozon_link.rfind('product/')

        ozon_product_id = ozon_link[(_idx + len(_prefix)):]

    await state.update_data(ozon_product_id=ozon_product_id)

    print('do request')

    try:
        async with aiohttp.ClientSession() as aiosession:
            # _url = f"http://5.61.53.235:1441/product/{message.text}"
            _url = f"http://172.18.0.4:8080/product/{ozon_product_id}"

            response = await aiosession.get(url=_url)

            print(response.status)

            res = await response.text()

            # print(res)

            w = re.findall(r'\"cardPrice.*currency?', res)
            print(w)

            if w:
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

                await state.update_data(ozon_start_price=_d.get('cardPrice', 0))
                await state.update_data(ozon_actual_price=_d.get('cardPrice', 0))

                price_text = '|'.join(str(v) for v in _d.items())
            else:
                _text = 'Возникли проблемы'
        
        _product_price = _d.get('cardPrice')
        example_percent = 10
        example_different = (_product_price * example_percent) / 100
        example_price = _product_price - example_different

        _text = f'Основная цена товара: {_product_price}\nАктуальная цена товара: {_product_price}\nВведите <b>процент как число</b>.\nКогда цена товара снизится <b>на этот процент или ниже</b>, мы сообщим Вам.\n\nПример:\n   Процент: {example_percent}\n   Ожидаемая(или ниже) цена товара: {_product_price} - {example_different} = {example_price}'

        # _text = f'Ваш продукт\n{message.text}\nЦена продукта: {price_text}'

        await state.update_data(ozon_product=message.text)

        await state.set_state(OzonProduct.percent)

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
        print(ex)
        pass
        

@ozon_router.message(OzonProduct.percent)
async def proccess_ozon_percent(message: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot):
    percent = message.text.strip()

    if percent == '/start':
        await clear_state_and_redirect_to_start(message,
                                                state,
                                                bot)
        await message.delete()
        return
    
    data = await state.get_data()

    msg = data.get('msg')
    

    await state.update_data(percent=percent)

    _kb = create_done_kb(marker='ozon_product')
    _kb = create_or_add_cancel_btn(_kb)

    link = data.get('ozon_link')
    start_price = data.get('ozon_start_price')
    product_price = data.get('ozon_actual_price')

    waiting_price = float(product_price) - ((float(product_price) * int(percent) / 100))

    _text = f'Ваш товар: {link}\nНачальная цена: {start_price}\nАктуальная цена: {product_price}\nпроцент: {percent}\nОжидаемая цена: {waiting_price}'

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await message.answer(text=_text,
                             reply_markup=_kb.as_markup())

    await message.delete()


@ozon_router.callback_query(F.data == 'list_product')
async def list_product(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot):
    data = await state.get_data()

    marker = data.get('action')
    user_id = callback.from_user.id

    subquery = (
        select(UserJob.job_id,
               UserJob.user_id,
               UserJob.product_id)
        .where(UserJob.user_id == callback.from_user.id)
    ).subquery()

    query = (
        select(
            OzonProductModel.id,
            OzonProductModel.link,
            OzonProductModel.actual_price,
            OzonProductModel.start_price,
            OzonProductModel.user_id,
            OzonProductModel.time_create,
            OzonProductModel.percent,
            subquery.c.job_id)\
        .select_from(OzonProductModel)\
        .join(User,
              OzonProductModel.user_id == User.tg_id)\
        .join(UserJob,
              UserJob.user_id == User.tg_id)\
        .outerjoin(subquery,
                   subquery.c.product_id == OzonProductModel.id)\
        .where(User.tg_id == callback.from_user.id)\
        .distinct(OzonProductModel.id)
    )

    async with session as _session:
        res = await _session.execute(query)

        _data = res.fetchall()

    print('ozon products22',_data)

    if not _data:
        await callback.answer(text='Сначала добавьте товар',
                              show_alert=True)
        return

#
    await state.update_data(ozon_product_idx=0,
                            ozon_product_list=_data)
    
    await show_item(callback,
                    state)
    return

#
    query = (
        select(
            OzonProductModel.id,
            OzonProductModel.link,
            OzonProductModel.actual_price,
            OzonProductModel.start_price,
            OzonProductModel.percent,
            OzonProductModel.time_create,
            OzonProductModel.user_id)\
        .join(User,
              OzonProductModel.user_id == User.tg_id)\
        .where(User.tg_id == user_id)
    )
    # async with session as session:
    async with session as session:
        ozon_product = await session.execute(query)

        ozon_product = ozon_product.fetchall()

    if not ozon_product:
        await callback.answer(text='Нет добавленных Ozon товаров',
                              show_alert=True)
        return

    ozon_product = ozon_product[0]

    _id, link, actual_price, start_price, percent, time_create, _user_id = ozon_product

    # Преобразование времени в московскую временную зону
    time_create: datetime
    moscow_tz = pytz.timezone('Europe/Moscow')
    moscow_time = time_create.astimezone(moscow_tz)

    job_id_query = (
        select(
            UserJob.job_id,
        )\
        .join(User,
              UserJob.user_id == User.tg_id)
        .where(
            and_(
                User.tg_id == callback.from_user.id,
                UserJob.product_marker == f"{marker}_product",
                UserJob.product_id == _id,
            )
        )
    )

    async with session as session:
        res = await session.execute(job_id_query)

        job_id = res.scalar_one_or_none()

    if not job_id:
        await callback.answer('error', show_alert=True)
        return

    # ozon_product = ozon_product[0]

    # print('ozon product', ozon_product.user_id, ozon_product.user, ozon_product.link)

    if ozon_product:
        _kb = create_remove_kb(user_id=callback.from_user.id,
                            product_id=_id,
                            marker='ozon',
                            job_id=job_id)
        _kb = create_or_add_cancel_btn(_kb)
        waiting_price = actual_price - ((actual_price * percent) / 100)

        _text = f'Привет {user_id}\nТвой WB <a href="{link}">товар</a>\nНачальная цена: {start_price}\nАктуальная цена: {actual_price}\nВыставленный процент: {percent}\nОжидаемая(или ниже) цена товара:{waiting_price}\nДата начала отслеживания: {moscow_time}'

        await callback.message.edit_text(text=_text,
                                         reply_markup=_kb.as_markup())
    else:
        await callback.answer('не получилось')

    # data = await state.get_data()

    # _kb = create_or_add_cancel_btn()

    # msg = data.get('msg')

    # ozon_product = data.get('ozon_product')

    # if ozon_product:
    #     _text = f'Ваш Ozon товар:\n{ozon_product}'
    #     if msg:
    #         await bot.edit_message_text(chat_id=callback.message.chat.id,
    #                                     text=_text,
    #                                     message_id=msg.message_id,
    #                                     reply_markup=_kb.as_markup())
    #     else:
    #         await bot.send_message(chat_id=callback.message.chat.id,
    #                                text=_text,
    #                                reply_markup=_kb.as_markup())
    # else:
    #     await callback.answer(text='Нет добавленных Ozon товаров',
    #                           show_alert=True)


# @ozon_router.message(F.text == 'test_ozon_pr')
# async def test_db_ozon(message: types.Message,
#                        session: AsyncSession):
#     user_id = message.from_user.id

#     query = (
#         select(OzonProductModel)\
#         .join(User,
#               OzonProductModel.user_id == User.id)\
#         .where(User.id == user_id)
#     )

#     ozon_product = await session.execute(query)

#     ozon_product = ozon_product.scalar_one_or_none()

#     print('ozon product', ozon_product)

#     if ozon_product:
#         await message.answer(f'привет {ozon_product.user_id}, {ozon_product.user}, {ozon_product.link}, {ozon_product.actual_price}')