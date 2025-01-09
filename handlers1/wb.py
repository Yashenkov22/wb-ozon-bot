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

from db.base import WbProduct, WbPunkt, User


wb_router = Router()


# @wb_router.callback_query(F.data == 'add_punkt')
# async def add_punkt(callback: types.Message | types.CallbackQuery,
#                     state: FSMContext,
#                     session: AsyncSession,
#                     bot: Bot):
#     await state.set_state(SwiftSepaStates.coords)
#     data = await state.get_data()

#     query = (
#         select(
#             WbPunkt.id
#         )\
#         .join(User,
#               WbPunkt.user_id == User.tg_id)\
#         .where(User.tg_id == callback.from_user.id)
#     )

#     res = await session.execute(query)

#     _wb_punkt = res.scalar_one_or_none()

#     if _wb_punkt:
#         await callback.answer(text='Пункт выдачи уже добален',
#                               show_alert=True)
        
#         return

#     msg: types.Message = data.get('msg')
#     _text = 'Введите координаты пункта доставки в формате: latitude, longitude\nПример: 59.915643, 30.402345'

#     _kb = create_or_add_cancel_btn()

#     if msg:
#         await bot.edit_message_text(text=_text,
#                                     chat_id=msg.chat.id,
#                                     message_id=msg.message_id,
#                                     reply_markup=_kb.as_markup())
#     else:
#         await callback.message.answer(text=_text,
#                              reply_markup=_kb.as_markup())


@wb_router.callback_query(F.data == 'add_punkt')
async def add_punkt(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot):
    
    lat, lon = ('55.707106', '37.572854')

    # await state.set_state(SwiftSepaStates.coords)
    data = await state.get_data()

    query = (
        select(
            WbPunkt.id
        )\
        .join(User,
              WbPunkt.user_id == User.tg_id)\
        .where(User.tg_id == callback.from_user.id)
    )

    async with session as session:
        res = await session.execute(query)

        _wb_punkt = res.scalar_one_or_none()

    if _wb_punkt:
        await callback.answer(text='Пункт выдачи уже добален',
                              show_alert=True)
        
        return
    

    async with aiohttp.ClientSession() as aiosession:
        _url = f"http://172.18.0.2:8080/pickUpPoint/{lat}/{lon}"
        response = await aiosession.get(url=_url)

        res = await response.json()

        deliveryRegions = res.get('deliveryRegions')

        print(deliveryRegions)

        del_zone = deliveryRegions[-1]
    
        _data = {
            'lat': float(lat),
            'lon': float(lon),
            'zone': del_zone,
            'user_id': callback.from_user.id,
            'time_create': datetime.now(),
        }

        query = (
            insert(WbPunkt)\
            .values(**_data)
        )
        async with session as session:
            await session.execute(query)

            try:
                await session.commit()
                _text = 'Wb пукнт успешно добавлен'
            except Exception:
                await session.rollback()
                _text = 'Wb пукнт не удалось добавить'

    # _text = f"Ваши данные:\nШирота: {lat}\nДолгота: {lon}\nЗона доставки: {del_zone}"

    await state.update_data(del_zone=del_zone)

    _kb = create_or_add_cancel_btn()

    await callback.message.edit_text(text=_text,
                                        reply_markup=_kb.as_markup())

    # if msg:
    #     await bot.edit_message_text(text=_text,
    #                                 chat_id=msg.chat.id,
    #                                 message_id=msg.message_id,
    #                                 reply_markup=_kb.as_markup())
    # else:
    #     await message.answer(text=_text,
    #                          reply_markup=_kb.as_markup())
        
    # await message.delete()

    # msg: types.Message = data.get('msg')
    # _text = 'Введите координаты пункта доставки в формате: latitude, longitude\nПример: 59.915643, 30.402345'

    # _kb = create_or_add_cancel_btn()

    # if msg:
    #     await bot.edit_message_text(text=_text,
    #                                 chat_id=msg.chat.id,
    #                                 message_id=msg.message_id,
    #                                 reply_markup=_kb.as_markup())
    # else:
    #     await callback.message.answer(text=_text,
    #                          reply_markup=_kb.as_markup())


@wb_router.message(SwiftSepaStates.coords)
async def proccess_lat(message: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
    coords = message.text
    await state.update_data(coords=coords)
    # await state.set_state(SwiftSepaStates.lon)
    data = await state.get_data()

    msg: types.Message = data.get('msg')
    # _text = 'Введите долготу пункта доставки'

    _kb = create_done_kb(marker='wb_punkt')

    _kb = create_or_add_cancel_btn(_kb)

    data = await state.get_data()

    lat, lon = coords.split()
    lat = lat[:-1]

    await state.update_data(lat=lat,
                            lon=lon)
    
    async with aiohttp.ClientSession() as aiosession:
        _url = f"http://172.18.0.2:8080/pickUpPoint/{lat}/{lon}"
        response = await aiosession.get(url=_url)

        res = await response.json()

        deliveryRegions = res.get('deliveryRegions')

        print(deliveryRegions)

        del_zone = deliveryRegions[-1]

    _text = f"Ваши данные:\nШирота: {lat}\nДолгота: {lon}\nЗона доставки: {del_zone}"

    await state.update_data(del_zone=del_zone)

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await message.answer(text=_text,
                             reply_markup=_kb.as_markup())
        
    await message.delete()


@wb_router.callback_query(F.data == 'list_punkt')
async def list_punkt(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot):
    data = await state.get_data()

    # _list_punkt = data.get('list_punkt')
    query = (
        select(
            WbPunkt.lat,
            WbPunkt.lon,
            WbPunkt.time_create,
            User.username,
            User.first_name,
            User.last_name,
        )\
        .join(User,
              WbPunkt.user_id == User.tg_id)\
        .where(User.tg_id == callback.from_user.id)
    )

    async with session as session:
        res = await session.execute(query)

        wb_punkt_data = res.fetchall()

    if wb_punkt_data:
        lat, lon, time_create, username, first_name, last_name = wb_punkt_data

        _user = username if username else f'{first_name} {last_name}'

        _text = f'Ваш пункт выдачи\nКоординаты: {lat}, {lon}\nПользователь: {_user}\nВремя добавления пункта выдачи: {time_create}'

    # if _list_punkt:
    #     _text = ''
    #     for _id, punkt in enumerate(_list_punkt, start=1):
    #         _sub_text = f'{_id}. Широта: {punkt[0]}, Долгота: {punkt[-1]}'
    #         _text += _sub_text + '\n'
    # else:
    #     _text = 'Нет добавленных пунктов'

        msg: types.Message = data.get('msg')

        _kb = create_or_add_cancel_btn()

        if msg:
            await bot.edit_message_text(text=_text,
                                        chat_id=msg.chat.id,
                                        message_id=msg.message_id,
                                        reply_markup=_kb.as_markup())
        else:
            await callback.message.answer(text=_text,
                                reply_markup=_kb.as_markup())
        


@wb_router.callback_query(F.data == 'check_price')
async def check_price_wb(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot):
    data = await state.get_data()
    msg: types.Message = data.get('msg')

    query = (
        select(WbPunkt.zone)\
        .join(User,
              WbPunkt.user_id == User.tg_id)\
        .where(User.tg_id == callback.from_user.id)
    )
    async with session as session:
        res = await session.execute(query)

        del_zone = res.scalar_one_or_none()

        if not del_zone:
            await callback.answer(text='Не получилось найти пункт выдачи',
                                show_alert=True)
            return

        # if not data.get('lat') or not data.get('lon'):
        #     await callback.answer(text='Сначала добавьте пункт выдачи',
        #                           show_alert=True)
        #     # await start(callback,
        #     #             state,
        #     #             bot)
        #     return

        query = (
            select(
                WbProduct.id
            )\
            .join(User,
                WbProduct.user_id == User.tg_id)\
            .where(User.tg_id == callback.from_user.id)
        )

        res = await session.execute(query)

        check_product_by_user = res.scalar_one_or_none()

    if check_product_by_user:
        await callback.answer(text='Продукт уже добален',
                              show_alert=True)
        return

    await state.set_state(ProductStates._id)
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
        

@wb_router.message(ProductStates._id)
async def proccess_product_id(message: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot):
    wb_product_link = message.text

    _prefix = 'catalog/'

    _idx_prefix = wb_product_link.find(_prefix)

    wb_product_id = wb_product_link[_idx_prefix + len(_prefix):].split('/')[0]

    # await state.update_data(wb_product_link=wb_product_link)
    # await state.update_data(wb_product_id=wb_product_id)
    data = await state.get_data()

    # lat, lon = data.get('list_punkt')[0]

    msg: types.Message = data.get('msg')

    query = (
        select(WbPunkt.zone)\
        .join(User,
              WbPunkt.user_id == User.tg_id)\
        .where(User.tg_id == message.from_user.id)
    )
    async with session as session:
        res = await session.execute(query)

        del_zone = res.scalar_one_or_none()

    if not res:
        await message.answer('Не получилось найти пункт выдачи')
        return

    # print('beginning')

    async with aiohttp.ClientSession() as aiosession:
        # _url = f"http://172.18.0.2:8080/pickUpPoint/{lat}/{lon}"
        # response = await aiosession.get(url=_url)

        # res = await response.json()

        # deliveryRegions = res.get('deliveryRegions')

        # print(deliveryRegions)

        # del_zone = deliveryRegions[-1]

        _url = f"http://172.18.0.2:8080/product/{del_zone}/{wb_product_id}"
        response = await aiosession.get(url=_url)
        res = await response.json()

        d = res.get('data')

        print(d.get('products')[0].get('sizes'))

        sizes = d.get('products')[0].get('sizes')

        _basic_price = _product_price = None
        
        for size in sizes:
            _price = size.get('price')
            if _price:
                _basic_price = size.get('price').get('basic')
                _product_price = size.get('price').get('product')

                _basic_price = str(_basic_price)[:-2]
                _product_price = str(_product_price)[:-2]

                print('основная:', _basic_price)
                print('актупльная:', _product_price)

                await state.update_data(wb_product_link=wb_product_link)
                await state.update_data(wb_product_id=wb_product_id)
                await state.update_data(wb_basic_price=float(_basic_price))
                await state.update_data(wb_product_price=float(_product_price))
                # await state.update_data(wb_del_zone=del_zone)


        # sizes = d.get('products')[0].get('sizes')[0]

        # basic_price = sizes.get('price').get('basic')

        # product_price = sizes.get('price').get('product')

        # print(price)
        # if _basic_price and _product_price:
        #     query = (
        #         select(WbPunkt.id)\
        #         .join(User,
        #               WbPunkt.user_id == User.id)\
        #         .where(User.id == message.from_user.id)
        #     )

        #     _wb_punkt_id = await session.execute(query)

        #     _wb_punkt_id = _wb_punkt_id.scalar_one_or_none()

        #     if _wb_punkt_id:
        #         data = {
        #             'link': wb_product_link,
        #             'short_link': wb_product_id,
        #             'basic_price': _basic_price,
        #             'actual_price': _product_price,
        #             'time_create': datetime.now(),
        #             'user_id': message.from_user.id,
        #             'wb_punkt_id': _wb_punkt_id,
        #         }
                
        #         query = (
        #             insert(WbProduct)\
        #             .values(**data)
        #         )
        #         await session.execute(query)

        #         try:
        #             await session.commit()
        #         except Exception as ex:
        #             print(ex)
                _text = f'Основная цена товара: {_basic_price}\nАктуальная цена товара: {_product_price}'
            else:
                _text = 'Не удалось найти цену товара'
        # for key in d.get('products')[0].get('sizes'):
        #     print(key)
        
        # print(res)

    _kb = create_done_kb(marker='wb_product')
    _kb = create_or_add_cancel_btn(_kb)

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await message.answer(text=_text,
                             reply_markup=_kb.as_markup())

    await message.delete()


@wb_router.callback_query(F.data == 'view_price')
async def view_price_wb(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot):
    data = await state.get_data()
    msg: types.Message = data.get('msg')

    # if not data.get('lat') or not data.get('lon'):
    #     await callback.answer(text='Сначала добавьте пункт выдачи',
    #                           show_alert=True)
    #     # await start(callback,
    #     #             state,
    #     #             bot)
    #     return

    # await state.set_state(ProductStates._id)
    # _text = 'Отправьте ссылку на товар'

    query = (
        select(WbProduct.link,
               WbProduct.actual_price,
               WbProduct.basic_price,
               WbProduct.user_id,
               WbProduct.time_create,
               WbPunkt.zone)\
        .select_from(WbProduct)\
        .join(User,
              WbProduct.user_id == User.tg_id)\
        .join(WbPunkt,
                User.tg_id == WbPunkt.user_id)\
        .where(User.tg_id == callback.from_user.id)
    )

    async with session as session:
        res = await session.execute(query)

        _data = res.fetchall()

    print(_data)

    if not _data:
        await callback.answer(text='Сначала добавьте товар',
                              show_alert=True)
        return

    wb_product_detail = _data[0]

    link, actaul_price, basic_price, user_id, time_create, zone = wb_product_detail

    _text = f'Привет {user_id}\nТвой WB товар\n{link}\nЗона доставки: {zone}\nОсновная цена: {basic_price}\nАктуальная цена: {actaul_price}\nДата начала отслеживания: {time_create}'

    _kb = create_or_add_cancel_btn()

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await callback.message.answer(text=_text,
                             reply_markup=_kb.as_markup())

# @wb_router.callback_query(F.data.startswith('done'))
# async def add_punkt_callback_done(callback: types.Message | types.CallbackQuery,
#                                     state: FSMContext,
#                                     session: AsyncSession,
#                                     bot: Bot,
#                                     scheduler: AsyncIOScheduler):
#     data = await state.get_data()

#     action = data.get('action')
#     callback_data = callback.data.split('__')[-1]

#     _text = await save_data_to_storage(callback,
#                                         state,
#                                         callback_data)
    
#     await callback.answer(text=_text,
#                           show_alert=True)
    
#     await redirect_to_(callback,
#                        state,
#                        bot,
#                        marker=action)
    
    # await callback.answer(text='Пункт выдачи добавлен.',
    #                       show_alert=True)
    # await start(callback,
    #             state,
    #             session,
    #             bot,
    #             scheduler)