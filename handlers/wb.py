import os
import json
import re

import aiohttp

import pytz

from datetime import datetime, timezone

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

from keyboards import (create_start_kb,
                       create_or_add_cancel_btn,
                       create_done_kb,
                       create_wb_start_kb,
                       add_back_btn,
                       create_bot_start_kb,
                       create_remove_kb)

from states import SwiftSepaStates, ProductStates, OzonProduct

from utils.handlers import (generate_pretty_amount,
                            save_data_to_storage,check_user,
                            clear_state_and_redirect_to_start,
                            generate_sale_for_price)

from db.base import UserJob, WbProduct, WbPunkt, User


wb_router = Router()


@wb_router.callback_query(F.data == 'add_punkt')
async def add_punkt(callback: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot):
    
    lat, lon = ('55.707106', '37.572854')

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
            'time_create': datetime.now(tz=pytz.timezone('Europe/Moscow')),
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


@wb_router.message(SwiftSepaStates.coords)
async def proccess_lat(message: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    bot: Bot):
    coords = message.text
    await state.update_data(coords=coords)
    # await state.set_state(SwiftSepaStates.lon)
    data = await state.get_data()

    msg: tuple = data.get('msg')
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
                                    chat_id=msg[0],
                                    message_id=msg[-1],
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
        lat, lon, time_create, username, first_name, last_name = wb_punkt_data[0]

        # Преобразование времени в московскую временную зону
        time_create: datetime
        moscow_tz = pytz.timezone('Europe/Moscow')
        moscow_time = time_create.astimezone(moscow_tz)

        _user = username if username else f'{first_name} {last_name}'

        _text = f'Ваш пункт выдачи\nКоординаты: {lat}, {lon}\nПользователь: {_user}\nВремя добавления пункта выдачи: {moscow_time}'

    else:
        _text = 'Нет добавленных пунктов'

    msg: tuple = data.get('msg')

    _kb = create_or_add_cancel_btn()

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg[0],
                                    message_id=msg[-1],
                                    reply_markup=_kb.as_markup())
    else:
        await callback.message.answer(text=_text,
                            reply_markup=_kb.as_markup())        


@wb_router.callback_query(F.data == 'add_wb_product')
async def add_wb_product(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot):
    data = await state.get_data()
    msg: tuple = data.get('msg')

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

    #     query = (
    #         select(
    #             WbProduct.id
    #         )\
    #         .join(User,
    #             WbProduct.user_id == User.tg_id)\
    #         .where(User.tg_id == callback.from_user.id)
    #     )

    #     res = await session.execute(query)

    #     check_product_by_user = res.scalar_one_or_none()

    # if check_product_by_user:
    #     await callback.answer(text='Продукт уже добален',
    #                           show_alert=True)
    #     return

    await state.set_state(ProductStates._id)
    _text = 'Отправьте ссылку на товар'

    _kb = create_or_add_cancel_btn()

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg[0],
                                    message_id=msg[-1],
                                    reply_markup=_kb.as_markup())
    else:
        await callback.message.answer(text=_text,
                             reply_markup=_kb.as_markup())
        

@wb_router.message(ProductStates._id)
async def proccess_product_id(message: types.Message | types.CallbackQuery,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot):
    # wb_product_link = message.text.strip()
    _message_text = message.text.strip().split()

    _name = link = None

    if len(_message_text) > 1:
        *_name, link = _message_text
        _name = ' '.join(_name)
    else:
        # if not message_text.isdigit():
        link = message.text.strip()
        # _name = 'Отсутствует'

    if message.text == '/start':
        await clear_state_and_redirect_to_start(message,
                                                state,
                                                bot)
        await message.delete()
        return

    _prefix = 'catalog/'

    _idx_prefix = link.find(_prefix)

    wb_product_id = link[_idx_prefix + len(_prefix):].split('/')[0]

    data = await state.get_data()

    msg: tuple = data.get('msg')

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
    
    query = (
        select(
            WbProduct.id
        )\
        .where(
            and_(
                WbProduct.user_id == message.from_user.id,
                WbProduct.link == link,
            )
        )
    )
    async with session as session:
        res = await session.execute(query)

        check_product_by_user = res.scalar_one_or_none()

    if check_product_by_user:
        _kb = create_or_add_cancel_btn()
        await bot.edit_message_text(chat_id=msg[0],
                                    message_id=msg[-1],
                                    text='Продукт уже добавлен ранее',
                                    reply_markup=_kb.as_markup())
        await message.delete()
        await state.set_state()
        return
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession() as aiosession:
            _url = f"http://172.18.0.2:8080/product/{del_zone}/{wb_product_id}"
            async with aiosession.get(url=_url,
                                        timeout=timeout) as response:
            # response = await aiosession.get(url=_url)

                try:
                    res = await response.json()
                    print(res)
                except Exception as ex:
                    print('API RESPONSE ERROR', ex)
                    await message.answer('ошибка при запросе к апи\n/start')
                    return

        d = res.get('data')

        # print(d.get('products')[0].get('sizes'))

        sizes = d.get('products')[0].get('sizes')

        product_name = d.get('products')[0].get('name')

        print('WB PARSED NAME', product_name)

        product_name = _name if _name else product_name

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

                _product_price = float(_product_price)

                await state.update_data(wb_product_link=link,
                                        wb_product_id=wb_product_id,
                                        wb_start_price=float(_product_price),
                                        wb_product_price=float(_product_price),
                                        wb_product_name=product_name)
                # await state.update_data(wb_product_id=wb_product_id)
                # await state.update_data(wb_start_price=float(_product_price))
                # await state.update_data(wb_product_price=float(_product_price))
                # await state.update_data(wb_product_name=_product_name)

                await state.set_state(ProductStates.percent)

                example_sale = 100
                # example_different = (_product_price * example_percent) / 100
                example_price = _product_price - example_sale

                _text = f'Основная цена товара: {_basic_price}\nАктуальная цена товара: {_product_price}\nВведите <b>скидку как число</b>.\nКогда цена товара снизится <b>на эту сумму или ниже</b>, мы сообщим Вам.\n\nПример:\n   Скидка: {example_sale}\n   Ожидаемая(или ниже) цена товара: {_product_price} - {example_sale} = {example_price}'
                break
            else:
                _text = 'Не удалось найти цену товара'
                print(_text)
                await message.answer(text=f'{_text}. Ожидается ссылка, передано {message.text}')
                await clear_state_and_redirect_to_start(message,
                                                        state,
                                                        bot)
                await message.delete()
                return
    except Exception as ex:
        print(ex)
        try:
            await message.delete()
            return
        except Exception:
            pass

    sale = generate_sale_for_price(_product_price)

    await state.update_data(sale=float(sale))

    _kb = create_done_kb(marker='wb_product')
    _kb = create_or_add_cancel_btn(_kb)

    # link = data.get('wb_product_link')
    start_price = _product_price
    product_price = _product_price

    waiting_price = float(product_price) - float(sale)


    _text_start_price = generate_pretty_amount(start_price)
    _text_product_price = generate_pretty_amount(product_price)

    _text_sale = generate_pretty_amount(sale)
    _text_price_with_sale = generate_pretty_amount((start_price - sale))
    # _text_basic_price = generate_pretty_amount(_d.get("price", 0))

    # _text = f'Ваш товар: {link}\nНачальная цена: {start_price}\nАктуальная цена: {product_price}\nСкидка: {sale}\nОжидаемая цена: {waiting_price}'

    _text = f'Название: <a href="{link}">{product_name}</a>\nМаркетплейс: WB\n\nНачальная цена: {_text_start_price}\nАктуальная цена: {_text_product_price}\n\nОтслеживается изменение цены на: {_text_sale}\nОжидаемая цена: {_text_price_with_sale}'

    if msg:
        try:
            await bot.edit_message_text(text=_text,
                                        chat_id=msg[0],
                                        message_id=msg[-1],
                                        reply_markup=_kb.as_markup())
        except Exception:
            await message.answer(text=_text,
                                reply_markup=_kb.as_markup())
    else:
        await message.answer(text=_text,
                             reply_markup=_kb.as_markup())
    try:
        await message.delete()
    except Exception:
        pass

    # _kb = create_or_add_cancel_btn()

    # if msg:
    #     await bot.edit_message_text(text=_text,
    #                                 chat_id=msg[0],
    #                                 message_id=msg[-1],
    #                                 reply_markup=_kb.as_markup())
    # else:
    #     await message.answer(text=_text,
    #                          reply_markup=_kb.as_markup())

    # await message.delete()



@wb_router.message(ProductStates.percent)
async def proccess_push_price(message: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot):
    sale = message.text.strip()

    if sale == '/start':
        await clear_state_and_redirect_to_start(message,
                                                state,
                                                bot)
        await message.delete()
        return
    
    data = await state.get_data()

    msg = data.get('msg')
    

    await state.update_data(sale=float(sale))

    _kb = create_done_kb(marker='wb_product')
    _kb = create_or_add_cancel_btn(_kb)

    link = data.get('wb_product_link')
    start_price = data.get('wb_start_price')
    product_price = data.get('wb_product_price')

    waiting_price = float(product_price) - float(sale)

    _text = f'Ваш товар: {link}\nНачальная цена: {start_price}\nАктуальная цена: {product_price}\nСкидка: {sale}\nОжидаемая цена: {waiting_price}'

    if msg:
        try:
            await bot.edit_message_text(text=_text,
                                        chat_id=msg[0],
                                        message_id=msg[-1],
                                        reply_markup=_kb.as_markup())
        except Exception:
            await message.answer(text=_text,
                                reply_markup=_kb.as_markup())
    else:
        await message.answer(text=_text,
                             reply_markup=_kb.as_markup())
    try:
        await message.delete()
    except Exception:
        pass


# @wb_router.callback_query(F.data == 'view_price')
# async def view_price_wb(callback: types.Message | types.CallbackQuery,
#                         state: FSMContext,
#                         session: AsyncSession,
#                         bot: Bot):
#     data = await state.get_data()
#     msg: tuple = data.get('msg')

#     marker = data.get('action')

#     subquery = (
#         select(UserJob.job_id,
#                UserJob.user_id,
#                UserJob.product_id)
#         .where(UserJob.user_id == callback.from_user.id)
#     ).subquery()

#     query = (
#         select(WbProduct.id,
#                WbProduct.link,
#                WbProduct.actual_price,
#                WbProduct.start_price,
#                WbProduct.user_id,
#                WbProduct.time_create,
#                WbProduct.name,
#                WbProduct.sale,
#                subquery.c.job_id)\
#         .select_from(WbProduct)\
#         .join(User,
#               WbProduct.user_id == User.tg_id)\
#         .join(UserJob,
#               UserJob.user_id == User.tg_id)\
#         .outerjoin(subquery,
#                    subquery.c.product_id == WbProduct.id)\
#         .where(User.tg_id == callback.from_user.id)\
#         .distinct(WbProduct.id)
#     )


#     async with session as _session:
#         res = await _session.execute(query)

#         _data = res.fetchall()
#         _new_data = []
#         for _d in _data:
#             product_id, link, actual, start, user_id, _date, name, sale, job_id = _d
#             moscow_tz = pytz.timezone('Europe/Moscow')
            
#             date = _date.astimezone(moscow_tz).timestamp()
#             _new_data.append((product_id, link, actual, start, user_id, date, name, sale, job_id))
#                     # _now = datetime.now()
#                     # moscow_time = _now.astimezone(moscow_tz)

#                     # if time_delta >= datetime.fromtimestamp(last_action_time).astimezone(moscow_tz):
#     print(type(_new_data))
#     print('wb products22',(_new_data))

#     if not _data:
#         await callback.answer(text='Сначала добавьте товар',
#                               show_alert=True)
#         return

# #
#     await state.update_data(wb_product_idx=0,
#                             wb_product_list=_new_data)
    
#     # await show_item(callback,
#     #                 state)
    
#     await show_item_list(callback,
#                          state,
#                          bot)
#     return
# #
#     wb_product_detail = _data[0]

#     product_id, link, actaul_price, start_price, user_id, time_create, percent, job_id = wb_product_detail


    # job_id_query = (
    #     select(
    #         UserJob.job_id,
    #     )\
    #     .join(User,
    #           UserJob.user_id == User.tg_id)
    #     .where(
    #         and_(
    #             User.tg_id == callback.from_user.id,
    #             UserJob.product_marker == f"{marker}_product",
    #             UserJob.product_id == product_id,
    #         )
    #     )
    # )

    # async with session as session:
    #     res = await session.execute(job_id_query)

    #     job_id = res.scalar_one_or_none()

    # if not job_id:
    #     await callback.answer('error', show_alert=True)
    #     return

    # Преобразование времени в московскую временную зону
    # time_create: datetime
    # moscow_tz = pytz.timezone('Europe/Moscow')
    # moscow_time = time_create.astimezone(moscow_tz)

    # waiting_price = actaul_price - ((actaul_price * percent) / 100)

    # _text = f'Привет {user_id}\nТвой WB <a href="{link}">товар</a>\n\nНачальная цена: {start_price}\nАктуальная цена: {actaul_price}\nВыставленный процент: {percent}\nОжидаемая(или ниже) цена товара:{waiting_price}\nДата начала отслеживания: {moscow_time}'

    # # _kb = create_remove_kb(user_id=callback.from_user.id,
    # #                        product_id=product_id,
    # #                        marker='wb',
    # #                        job_id=job_id)
    # # _kb = create_or_add_cancel_btn(_kb)

    # if msg:
    #     await bot.edit_message_text(text=_text,
    #                                 chat_id=msg.chat.id,
    #                                 message_id=msg.message_id,
    #                                 reply_markup=_kb.as_markup())
    # else:
    #     await callback.message.answer(text=_text,
    #                          reply_markup=_kb.as_markup())
        

# @wb_router.callback_query(F.data.startswith('product'))
# async def init_current_item(callback: types.CallbackQuery,
#                             state: FSMContext):
#     action = callback.data.split('_')[-1]
#     data = await state.get_data()
#     product_idx = data['_idx_product']
#     print('idx from callback',product_idx)
#     match action:
#         case 'next':
#             await state.update_data(_idx_product=product_idx+1)
#         case 'prev':
#             await state.update_data(_idx_product=product_idx-1)
#     await show_item(callback, state)