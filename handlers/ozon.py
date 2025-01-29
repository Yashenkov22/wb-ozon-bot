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
from utils.handlers import (clear_state_and_redirect_to_start,
                            save_data_to_storage,
                            check_user,
                            show_item,
                            show_item_list,
                            generate_sale_for_price)

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

    msg: tuple = data.get('msg')
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
    
    await callback.answer()
        

@ozon_router.message(OzonProduct.product)
async def proccess_product(message: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot):
    # ozon_link = message.text.strip()
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

    data = await state.get_data()

    msg: tuple = data.get('msg')

    query = (
        select(
            OzonProductModel.id
        )\
        .join(User,
            OzonProductModel.user_id == User.tg_id)\
        .where(
            and_(
                User.tg_id == message.from_user.id,
                OzonProductModel.link == link,
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
                                    text='Продукт уже добавлен',
                                    reply_markup=_kb.as_markup())
        await message.delete()
        return True

    # _kb = create_done_kb(marker='ozon_product')

    #proccess_msg = await bot.send_message('Товар добавляется')

    _kb = create_or_add_cancel_btn()

    if link.startswith('https://ozon.ru/t/'):
        _idx = link.find('/t/')
        print(_idx)
        _prefix = '/t/'
        ozon_short_link = 'croppedLink|' + link[_idx+len(_prefix):]
        print(ozon_short_link)
    else:
        _prefix = 'product/'

        _idx = link.rfind('product/')

        ozon_short_link = link[(_idx + len(_prefix)):]

    # await state.update_data(ozon_link=link,
    #                         ozon_short_link=ozon_short_link)
    # await state.update_data(ozon_short_link=ozon_short_link)

    print('do request on OZON API')

    # sub_msg = await message.answer(text='Товар проверяется...')

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession() as aiosession:
            # _url = f"http://5.61.53.235:1441/product/{message.text}"
            _url = f"http://172.18.0.7:8080/product/{ozon_short_link}"

            # response = await aiosession.get(url=_url)
            async with aiosession.get(url=_url,
                                      timeout=timeout) as response:

                print(f'OZON RESPONSE CODE {response.status}')
                if response.status == 408:
                    print('OZON TIMEOUT')
                    # proccess_msg.edit_text('marker товар не получилось добавить, link')
                    await clear_state_and_redirect_to_start(message,
                                                            state,
                                                            bot)
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    
                    return

                res = await response.text()

        # print('ОТВЕТ ОТ АПИ',res)

        new_short_link = res.split('|')[0]

        await state.update_data(ozon_link=link,
                                ozon_short_link=new_short_link)


        w = re.findall(r'\"cardPrice.*currency?', res)
        # print(w)

        _alt = re.findall(r'\"alt.*,?', res)
        _product_name = None
        _product_name_limit = 21
        
        if _alt:
            # print('OZON PARSED ALT', _alt[0])
            _product_name = _alt[0].split(',')[0]
            _prefix = f'\"alt\":\"'
            
            # if _product_name.startswith(_prefix):
            # _product_name = _product_name[len(_prefix)+2:][:_product_name_limit]
            _product_name: str = _product_name[len(_prefix)+2:]

            _product_name = ' '.join([part_name for part_name in _product_name.split() \
                                      if part_name.isalnum()])

        print(_product_name)

        _product_name = _name if _name else _product_name

        await state.update_data(ozon_product_name=_product_name)
        # print('NAME   ',_alt[0].split('//')[0])

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
            await state.update_data(ozon_basic_price=_d.get('price', 0))

            price_text = '|'.join(str(v) for v in _d.items())

            # await sub_msg.edit_text(text='Товар проверен')
        else:
            _text = 'Возникли проблемы'
            # proccess_msg.edit_text('marker товар не получилось добавить, link')

            # await sub_msg.edit_text(text=f'{_text}. Ожидается ссылка, передано {message.text}')
            await clear_state_and_redirect_to_start(message,
                                                    state,
                                                    bot)
            await message.delete()
            return
        
        _product_price = _d.get('cardPrice')
        example_sale = 100
        # example_different = (_product_price * example_percent) / 100
        example_price = _product_price - example_sale

        # _text = f'Основная цена товара: {_product_price}\nАктуальная цена товара: {_product_price}\nВведите <b>скидку как число</b>.\nКогда цена товара снизится <b>на эту сумму или ниже</b>, мы сообщим Вам.\n\nПример:\n   Скидка: {example_sale}\n   Ожидаемая(или ниже) цена товара: {_product_price} - {example_sale} = {example_price}'

        # _text = f'Ваш продукт\n{message.text}\nЦена продукта: {price_text}'

        await state.update_data(ozon_product=message.text)  # ?

        # await state.set_state(OzonProduct.percent)

        _kb = create_done_kb(marker='ozon_product')
        _kb = create_or_add_cancel_btn(_kb)

        # link = data.get('ozon_link')
        start_price = _d.get('cardPrice')
        product_price = _d.get('cardPrice')

        sale = generate_sale_for_price(start_price)
        await state.update_data(sale=sale)

        waiting_price = float(product_price) - sale

        # _text = f'Ваш товар: {link}\nНачальная цена: {start_price}\nАктуальная цена: {product_price}\nУстановленная скидка: {sale}\nОжидаемая цена: {waiting_price}'

        _text = f'Название: <a href="{link}">{_product_name}</a>\nМаркетплейс: Ozon\n\nОсновная цена(без Ozon карты): {_d.get("price", 0)}\nНачальная цена: {start_price}\nАктуальная цена: {start_price}\n\nОтслеживается изменение цены на: {sale}\nОжидаемая цена: {start_price - sale}'


        if msg:
            await bot.edit_message_text(text=_text,
                                        chat_id=msg[0],
                                        message_id=msg[-1],
                                        reply_markup=_kb.as_markup())
        else:
            await message.answer(text=_text,
                                reply_markup=_kb.as_markup())

        await message.delete()
#

        if msg:
            await bot.edit_message_text(text=_text,
                                        chat_id=message.chat.id,
                                        message_id=msg[-1],
                                        reply_markup=_kb.as_markup())
        else:
            await bot.send_message(chat_id=message.chat.id,
                                text=_text,
                                reply_markup=_kb.as_markup())
            
    except Exception as ex:
        # proccess_msg.edit_text('marker товар не получилось добавить, link')
        print(ex)
        pass
    finally:
        try:
            await message.delete()
        except Exception:
            pass
        

@ozon_router.message(OzonProduct.percent)
async def proccess_ozon_percent(message: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot):
    sale = message.text.strip()

    if sale == '/start' or not sale.isdigit():
        await clear_state_and_redirect_to_start(message,
                                                state,
                                                bot)
        await message.delete()
        return
    
    sale = float(sale)

    data = await state.get_data()

    msg: tuple = data.get('msg')
    

    await state.update_data(sale=sale)

    _kb = create_done_kb(marker='ozon_product')
    _kb = create_or_add_cancel_btn(_kb)

    link = data.get('ozon_link')
    start_price = data.get('ozon_start_price')
    product_price = data.get('ozon_actual_price')

    waiting_price = float(product_price) - sale

    _text = f'Ваш товар: {link}\nНачальная цена: {start_price}\nАктуальная цена: {product_price}\nУстановленная скидка: {sale}\nОжидаемая цена: {waiting_price}'

    if msg:
        await bot.edit_message_text(text=_text,
                                    chat_id=msg[0],
                                    message_id=msg[-1],
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
            OzonProductModel.name,
            OzonProductModel.sale,
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

        _new_data = []
        for _d in _data:
            product_id, link, actual, start, user_id, _date, name, sale, job_id = _d
            moscow_tz = pytz.timezone('Europe/Moscow')
            
            date = _date.astimezone(moscow_tz).timestamp()
            _new_data.append((product_id, link, actual, start, user_id, date, name, sale, job_id))


    print('ozon products22',_data)

    if not _new_data:
        await callback.answer(text='Сначала добавьте товар',
                              show_alert=True)
        return

#
    await state.update_data(ozon_product_idx=0,
                            ozon_product_list=_new_data)
    
    # await show_item(callback,
    #                 state)
    await show_item_list(callback,
                         state,
                         bot)
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