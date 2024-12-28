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

from config import BEARER_TOKEN, FEEDBACK_REASON_PREFIX

from keyboards import (create_start_kb,
                       create_or_add_cancel_btn,
                       create_done_kb,
                       create_wb_start_kb,
                       add_back_btn,
                       create_bot_start_kb)

from states import SwiftSepaStates, ProductStates, OzonProduct
from utils.handlers import save_data_to_storage


main_router = Router()

start_text = '💱<b>Добро пожаловать в MoneySwap!</b>\n\nНаш бот поможет найти лучшую сделку под вашу задачу 💸\n\n👉🏻 <b>Чтобы начать поиск</b>, выберите категорию “безналичные”, “наличные” или “Swift/Sepa” и нажмите на нужную кнопку ниже.\n\nЕсли есть какие-то вопросы, обращайтесь <a href="https://t.me/MoneySwap_support">Support</a> или <a href="https://t.me/moneyswap_admin">Admin</a>. Мы всегда готовы вам помочь!'

moscow_tz = pytz.timezone('Europe/Moscow')


import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Это информационное сообщение")


@main_router.message(Command('start'))
async def start(message: types.Message | types.CallbackQuery,
                state: FSMContext,
                bot: Bot):
    
    logger.info('hi')
    
    await state.update_data(action=None)

    if isinstance(message, types.CallbackQuery):
        message = message.message

    _kb = create_start_kb()
    msg = await bot.send_message(text='Привет.\nЭто тестовые WB и OZON боты.',
                                 chat_id=message.chat.id,
                                reply_markup=_kb.as_markup())
    
    await state.update_data(msg=msg)

    await message.delete()


@main_router.callback_query(F.data == 'cancel')
async def callback_cancel(callback: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            bot: Bot):
    # await start(callback,
    #             state,
    #             bot)
    data = await state.get_data()

    action = data.get('action')

    await redirect_to_(callback,
                       state,
                       bot,
                       marker=action)


async def to_back(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
    await start(callback,
                state,
                bot)
    

@main_router.callback_query(F.data == 'to_main')
async def callback_cancel(callback: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            bot: Bot):
    # callback_data = callback.data.split('_')[-1]

    # await redirect_to_(callback,
    #               state,
    #               bot,
    #               marker='wb')
    await start(callback,
                state,
                bot)
    # await start(callback,
    #             state,
    #             bot)

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


# @main_router.callback_query(F.data == 'wb_bot')
# async def redirect_to_(callback: types.CallbackQuery,
#                         state: FSMContext,
#                         bot: Bot,
#                         marker: str = None):
#     if not marker:
#         marker = 'wb'

#     await state.update_data(action=marker)

#     data = await state.get_data()
#     msg = data.get('msg')

#     _text = 'Выберите действие'

#     _kb = create_wb_start_kb()

#     _kb = add_back_btn(_kb)

#     if msg:
#         await bot.edit_message_text(text=_text,
#                                     chat_id=callback.message.chat.id,
#                                     message_id=msg.message_id,
#                                     reply_markup=_kb.as_markup())
#     else:
#         await bot.send_message(chat_id=callback.message.chat.id,
#                                text=_text,
#                                reply_markup=_kb.as_markup())

@main_router.callback_query(F.data == 'add_product')
async def add_product(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
    await state.set_state(OzonProduct.product)
    data = await state.get_data()

    msg: types.Message = data.get('msg')
    _text = 'Введите идентификатор продукта\nПример : spetsialnoe-chistyashchee-sredstvo-dlya-posudomoechnoy-mashiny-intensivnyy-ochistitel-somat-intensve-1594468872/?avtc=1&avte=4&avts=1735371267'

    _kb = create_or_add_cancel_btn()

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await callback.message.answer(text=_text,
                             reply_markup=_kb.as_markup())
        

@main_router.callback_query(F.data == 'list_product')
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
        

@main_router.message(OzonProduct.product)
async def proccess_lat(message: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        bot: Bot):
    data = await state.get_data()

    msg: types.Message = data.get('msg')

    _kb = create_done_kb(marker='ozon_product')

    _kb = create_or_add_cancel_btn(_kb)

    await message.answer('beginning')
    try:
        async with aiohttp.ClientSession() as aiosession:
            # _url = f"http://5.61.53.235:1441/product/{message.text}"
            _url = f"http://5.61.53.235:1441/product/{message.text}"

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
                            price = price.split()[0]
                            print(price)
                            _d[k] = price
                            break
                else:
                    break

            print(_d)

            price_text = '|'.join(str(v) for v in _d.items())


            # for q in w:
            #     # print(q)
            #     for k in _d:
            #         if q.find(k) != -1:
            #             name, price = q.split(':')
            #             price = price.replace('\\', '').replace('"', '')
            #             print(price)
            #             break
    # {\"isAvailable\":true, \"cardPrice\":\"177 ₽\", \"price\":\"179 ₽\", \"originalPrice\":\"469 ₽\",

            # print(res)

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
        logger.info(ex)


@main_router.callback_query(F.data.startswith('done'))
async def callback_done(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
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
    


    # data = await state.get_data()

    # list_punkt = data.get('list_punkt', None)

    # if list_punkt is None:
    #     list_punkt = list()
    
    # list_punkt.append([data.get('lat'), data.get('lon')])

    # await state.update_data(list_punkt=list_punkt)
    # await state.set_state(SwiftSepaStates.lat)
    # data = await state.get_data()

    # msg: types.Message = data.get('msg')
    # _text = 'Введите широту пункта доставки'

    # _kb = create_or_add_cancel_btn()

    # if msg:
    #     await bot.edit_message_text(text=_text,
    #                                 chat_id=msg.chat.id,
    #                                 message_id=msg.message_id,
    #                                 reply_markup=_kb.as_markup())
    # else:
    #     await callback.message.answer(text=_text,
    #                          reply_markup=_kb.as_markup())
    await callback.answer(text='Пункт выдачи добавлен.',
                          show_alert=True)
    await start(callback,
                state,
                bot)


@main_router.callback_query(F.data == 'add_punkt')
async def add_punkt(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
    await state.set_state(SwiftSepaStates.coords)
    data = await state.get_data()

    msg: types.Message = data.get('msg')
    _text = 'Введите координаты пункта доставки в формате: latitude, longitude\nПример: 59.915643, 30.402345'

    _kb = create_or_add_cancel_btn()

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await callback.message.answer(text=_text,
                             reply_markup=_kb.as_markup())
        

@main_router.callback_query(F.data == 'list_punkt')
async def list_punkt(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
    data = await state.get_data()

    _list_punkt = data.get('list_punkt')

    if _list_punkt:
        _text = ''
        for _id, punkt in enumerate(_list_punkt, start=1):
            _sub_text = f'{_id}. Широта: {punkt[0]}, Долгота: {punkt[-1]}'
            _text += _sub_text + '\n'
    else:
        _text = 'Нет добавленных пунктов'

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


@main_router.message(SwiftSepaStates.coords)
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

    _text = f"Ваши данные:\nШирота: {lat}\nДолгота: {lon}"

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await message.answer(text=_text,
                             reply_markup=_kb.as_markup())
        
    await message.delete()
        


# @main_router.message(SwiftSepaStates.lon)
# async def proccess_lon(message: types.Message | types.CallbackQuery,
#                     state: FSMContext,
#                     bot: Bot):
#     lon = message.text
#     await state.update_data(lon=lon)
#     # await state.set_state(SwiftSepaStates.lon)
#     data = await state.get_data()

#     msg: types.Message = data.get('msg')
#     # _text = 'Введите долготу пункта доставки'

#     _kb = create_done_kb()

#     _kb = create_or_add_cancel_btn(_kb)
#     data = await state.get_data()

#     _text = f"Ваши данные:\nШирота: {data.get('lat')}\nДолгота: {data.get('lon')}"

#     if msg:
#         await bot.edit_message_text(text=_text,
#                                     chat_id=msg.chat.id,
#                                     message_id=msg.message_id,
#                                     reply_markup=_kb.as_markup())
#     else:
#         await message.answer(text=_text,
#                              reply_markup=_kb.as_markup())
        
#     await message.delete()


@main_router.callback_query(F.data == 'check_price')
async def check_price_wb(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
    data = await state.get_data()
    msg: types.Message = data.get('msg')

    if not data.get('lat') or not data.get('lon'):
        await callback.answer(text='Сначала добавьте пункт выдачи',
                              show_alert=True)
        # await start(callback,
        #             state,
        #             bot)
        return

    await state.set_state(ProductStates._id)
    _text = 'Введите идентификатор товара'

    _kb = create_or_add_cancel_btn()

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await callback.message.answer(text=_text,
                             reply_markup=_kb.as_markup())
        

@main_router.message(ProductStates._id)
async def proccess_product_id(message: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
    product_id = message.text
    await state.update_data(product_id=product_id)
    data = await state.get_data()

    lat, lon = data.get('list_punkt')[0]

    msg: types.Message = data.get('msg')

    print('beginning')

    async with aiohttp.ClientSession() as aiosession:
        _url = f"http://172.17.0.2:8080/pickUpPoint/{lat}/{lon}"
        response = await aiosession.get(url=_url)

        res = await response.json()

        deliveryRegions = res.get('deliveryRegions')

        print(deliveryRegions)

        del_zone = deliveryRegions[-1]

        _url = f"http://172.17.0.2:8080/product/{del_zone}/{product_id}"
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

                print('основная:', _basic_price)
                print('актупльная:', _product_price)


        # sizes = d.get('products')[0].get('sizes')[0]

        # basic_price = sizes.get('price').get('basic')

        # product_price = sizes.get('price').get('product')

        # print(price)
        if _basic_price and _product_price:
            _text = f'Основная цена товара: {str(_basic_price)[:-2]}\nАктуальная цена товара: {str(_product_price)[:-2]}'
        else:
            _text = 'Не удалось найти цену товара'
        # for key in d.get('products')[0].get('sizes'):
        #     print(key)
        
        # print(res)

    _kb = create_or_add_cancel_btn()

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg.chat.id,
                                    message_id=msg.message_id,
                                    reply_markup=_kb.as_markup())
    else:
        await message.answer(text=_text,
                             reply_markup=_kb.as_markup())

    await message.delete()