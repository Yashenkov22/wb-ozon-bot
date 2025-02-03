import asyncio
import json
import re

import aiohttp

from datetime import datetime, timedelta
from typing import Any

from asyncio import sleep

import pytz

from aiogram import types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import update, select, and_, or_, insert
from sqlalchemy.ext.asyncio import AsyncSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot22 import bot

from db.base import User, WbProduct, WbPunkt, OzonProduct, UserJob

from utils.scheduler import push_check_ozon_price, push_check_wb_price, scheduler_cron

from keyboards import (add_back_btn, add_pagination_btn,
                       create_or_add_cancel_btn, create_or_add_exit_btn,
                       create_photo_keyboard, create_product_list_for_page_kb, create_product_list_kb,
                       create_remove_kb,
                       add_cancel_btn_to_photo_keyboard)

from utils.storage import redis_client


DEFAULT_PAGE_ELEMENT_COUNT = 5

# lock = asyncio.Lock()


# def check_input_link(link: str):
#     return (link.startswith('https://ozon')) or \
#         (link.startswith('https://www.ozon')) or \
#         (link.startswith('https://www.wildberries'))


def check_input_link(link: str):
    if (link.startswith('https://ozon')) or \
        (link.startswith('https://www.ozon')) or \
        (link.startswith('https://www.wildberries')):
        
        return 'WB' if link.startswith('https://www.wildberries') else 'OZON'


def generate_sale_for_price(price: float):
    price = float(price)
    if 0 <= price <= 100:
        _sale = 10
    elif 100 < price <= 500:
        _sale = 50
    elif 500 < price <= 2000:
        _sale = 100
    elif 2000 < price <= 5000:
        _sale = 300
    else:
        _sale = 500
    
    return _sale


def generate_pretty_amount(price: str | float):
    _sign = '₽'
    price = int(price)

    pretty_price = f'{price:,}'.replace(',', ' ') + f' {_sign}'

    return pretty_price


async def check_user_last_message_time(user_id: int,
                                       now_time: datetime,
                                       message_text: str,
                                       session: AsyncSession,
                                       state: FSMContext,
                                       scheduler: AsyncIOScheduler):
        lock = asyncio.Lock()

        _message_text = message_text.strip().split()

        _name = link = None

        if len(_message_text) > 1:
            *_name, link = _message_text
            _name = ' '.join(_name)
        else:
            if not message_text.isdigit():
                link = message_text

        # key = f'fsm:{user_id}:{user_id}:data'
        # async with redis_client.pipeline(transaction=True) as pipe:
        async with lock:
                
            state_dict = {}

            # user_data: bytes = await pipe.get(key)
            user_data = await state.get_data()
            # Выполняем все команды в pipeline
            # results = await pipe.execute()
            # Извлекаем результат из выполненного pipeline
            # print(results)
            print(user_data)

            # user_data: dict = json.loads(results[0])

            if last_action_time := user_data.get('last_action_time'):
                print(user_data)
                moscow_tz = pytz.timezone('Europe/Moscow')
                _last_action_time = datetime.fromtimestamp(last_action_time).astimezone(moscow_tz)


                # #
                # user_data['percent'] = None
                # #

                time_delta = now_time - timedelta(seconds=10)
                
                moscow_tz = pytz.timezone('Europe/Moscow')
                
                print('ACTUAL TIME', now_time)
                print('LAST TIME FROM REDIS', _last_action_time)
                print('TIMEDELTA', time_delta)

                if time_delta >= datetime.fromtimestamp(last_action_time).astimezone(moscow_tz):
                    # first message
                    #
                    state_dict['percent'] = None
                    state_dict['last_action_time'] = now_time.timestamp()
                    #

                    print(f'first message {message_text}')
                    
                    # write last_action_time to redis
                    # user_data['last_action_time'] = now_time.timestamp()
                    # await state.update_data(state_dict)

                    # sub_user_data = json.dumps(user_data)
                    # await pipe.set(key, sub_user_data)
                    # await pipe.execute()

                    if message_text.isdigit():
                        state_dict['percent'] = message_text
                    else:
                        state_dict['link'] = link
                        state_dict['name'] = _name
                        user_data.update(state_dict)
                        await save_product(user_data,
                                            session,
                                            scheduler)
                        # save product without percent
                else:
                    # second message
                    print(f'second message {message_text}')
                    if message_text.isdigit():
                        print(user_data)
                        _percent = message_text
                        await add_procent_to_product(user_data,
                                                        session,
                                                        _percent)
                        # add percent to product
                    else:
                        print(user_data)
                        state_dict['link'] = link
                        state_dict['name'] = _name

                        percent = user_data.get('percent')
                        user_data.update(state_dict)

                        await save_product(user_data,
                                            session,
                                            scheduler,
                                            percent=percent)
                        # get percent from storage and save product with percent
                        
                    # user_data['last_action_time'] = now_time.timestamp()
                    # await state.update_data(state_dict)
                    pass
            else:
                # first message
                state_dict['percent'] = None

                print(f'first message {message_text}')
                print(user_data)
                
                # write last_action_time to redis
                state_dict['last_action_time'] = now_time.timestamp()
                # await state.update_data(state_dict)
                # sub_user_data = json.dumps(user_data)
                # await pipe.set(key, sub_user_data)
                # await pipe.execute()

                if message_text.isdigit():
                    state_dict['percent'] = message_text
                    pass
                else:
                    state_dict['link'] = link
                    state_dict['name'] = _name
                    user_data.update(state_dict)
                    await save_product(user_data,
                                        session,
                                        scheduler)
                    # save product without percent
                    pass

            await state.update_data(state_dict)
            print('state on end', await state.get_data())
                # user_data = json.dumps(user_data)
                # await pipe.set(key, user_data)

                # await pipe.execute()

    
    # query = (
    #     select(
    #         User
    #     )\
    #     .where(User.tg_id == user_id)
    # )

    # res = await session.execute(query)

    # user = res.scalar_one_or_none()

    # if user:
    #     moscow_tz = pytz.timezone('Europe/Moscow')
    #     _now = datetime.now()
    #     moscow_time = _now.astimezone(moscow_tz)
    #     _time_delta = moscow_time - timedelta(seconds=20)

    #     print(moscow_time , user.last_action_time.astimezone(moscow_tz))

    #     if user.last_action_time is not None \
    #         and user.last_action_time.astimezone(moscow_tz) >= _time_delta:
    #         return 'percent'
    #     else:
    #         # await sleep(1)
    #         return 'link'

async def add_procent_to_product(user_data: dict,
                                 session: AsyncSession,
                                 percent: str):
    msg = user_data.get('msg')
    link: str = user_data.get('link')

    if msg and link:
        if link.find('ozon') > 0:
            query = (
                update(
                    OzonProduct
                )\
                .values(percent=int(percent))
                .where(
                    and_(
                        OzonProduct.user_id == msg[0],
                        OzonProduct.link == link,
                    )
                )
            )

            await session.execute(query)

            try:
                print('percent updated')
                await session.commit()
            except Exception as ex:
                print(ex)
                print('update percent failed')
                await session.rollback()
            #add to ozon
        elif link.find('wildberries') > 0:
            query = (
                update(
                    WbProduct
                )\
                .values(percent=int(percent))
                .where(
                    and_(
                        WbProduct.user_id == msg[0],
                        WbProduct.link == link,
                    )
                )
            )

            await session.execute(query)

            try:
                print('percent updated')
                await session.commit()
            except Exception as ex:
                print(ex)
                print('update percent failed')
                await session.rollback()

            pass
        else:
            # error
            pass
    

        
async def save_product(user_data: dict,
                       session: AsyncSession,
                       scheduler: AsyncIOScheduler,
                       percent: str = None):
    msg = user_data.get('msg')
    _name = user_data.get('name')
    link: str = user_data.get('link')
    # percent: int = user_data.get('percent')

    if link.find('ozon') > 0:
        # save ozon product
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

        # await state.update_data(ozon_link=ozon_link,
        #                         ozon_short_link=ozon_short_link)
        # await state.update_data(ozon_short_link=ozon_short_link)

        query = (
            select(
                OzonProduct.id,
            )\
            .where(
                OzonProduct.user_id == msg[0],
                OzonProduct.link == link,
            )
        )
        async with session as _session:
            res = await _session.execute(query)

        res = res.scalar_one_or_none()

        if res:
            # await bot.send_message(chat_id=msg[0],
            #                        text='Товар уже добавлен')
            return True

        print('do request on OZON API')

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession() as aiosession:
                # _url = f"http://5.61.53.235:1441/product/{message.text}"
                _url = f"http://172.18.0.7:8080/product/{ozon_short_link}"
                async with aiosession.get(url=_url,
                            timeout=timeout) as response:

                # response = await aiosession.get(url=_url)
                    print(f'OZON RESPONSE CODE {response.status}')
                    if response.status == 408:
                        print('TIMEOUT')
                        await bot.send_message(chat_id=msg[0],
                                               text='Таймаут API')
                        return True

                    # print(f'OZON RESPONSE CODE {response.status}')

                    res = await response.text()

                # print(res)

            if res == '408 Request Timeout':
                await bot.send_message(chat_id=msg[0],
                                       text=f'status 200, text {res}')
                
                return True
            
            _new_short_link = res.split('|')[0]

            w = re.findall(r'\"cardPrice.*currency?', res)
            # print(w)

            _alt = re.findall(r'\"alt.*,?', res)
            _product_name = None
            _product_name_limit = 21
            
            if _alt:
                _product_name = _alt[0].split('//')[0]
                _prefix = f'\"alt\":\"'
                
                # if _product_name.startswith(_prefix):
                # _product_name = _product_name[len(_prefix)+2:][:_product_name_limit]
                _product_name = _product_name[len(_prefix)+2:]
                _product_name = ' '.join(_product_name.split()[:4])

            print(_product_name)

            # await state.update_data(ozon_product_name=_product_name)
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
                start_price = int(_d.get('cardPrice', 0))
                actual_price = int(_d.get('cardPrice', 0))
                basic_price = int(_d.get('price', 0))

                _name = _name if _name else _product_name
            else:
                print('22')
                try:
                    response_data = res.split('|')[-1]

                    json_data: dict = json.loads(response_data)

                    _name = ' '.join(json_data.get('seo').get('title').split()[:4])

                    script_list = json_data.get('seo').get('script')

                    # if v:
                    #     t = v.get('script')

                    # if script_list:
                    inner_html = script_list[0].get('innerHTML') #.get('offers').get('price')

                    print('innerHTML', inner_html)

                    # if inner_html:
                        # print(type(b))
                    try:
                        inner_html_json: dict = json.loads(inner_html)
                        offers = inner_html_json.get('offers')

                        # print(offers)

                        _price = offers.get('price')

                        start_price = int(_price)
                        actual_price = int(_price)
                        basic_price = int(_price)

                        # price_dict = {
                        #     'ozon_start_price': 0,
                        #     'ozon_actual_price': float(_p),
                        #     'ozon_basic_price': float(_p),
                        # }

                        # await state.update_data(data=price_dict)
                        
                        print('Price', _price)
                    except Exception as ex:
                        return True
                        print('problem', ex)

                    print('PRICE PARSE ERROR', user_data)
                except Exception as ex:
                    print(ex)
                    return True
#
            _sale = generate_sale_for_price(start_price)

            _data = {
                'link': link,
                'short_link': _new_short_link,
                'actual_price': actual_price,
                'start_price': start_price,
                'basic_price': basic_price,
                #
                'sale': _sale,
                #
                # 'percent': int(data.get('percent')),
                'name': _name,
                'time_create': datetime.now(),
                'user_id': msg[0],
            }

            # if percent:
            #     _data.update(percent=int(percent))
            
            # query = (
            #     insert(OzonProduct)\
            #     .values(**_data)
            # )

            # await session.execute(query)
            ozon_product = OzonProduct(**_data)

            session.add(ozon_product)

            await session.flush()

            ozon_product_id = ozon_product.id

            #          user_id | marker | product_id
            job_id = f'{msg[0]}.ozon.{ozon_product_id}'

            job = scheduler.add_job(push_check_ozon_price,
                            trigger='interval',
                            minutes=15,
                            id=job_id,
                            jobstore='sqlalchemy',
                            coalesce=True,
                            kwargs={'user_id': msg[0],
                                    'product_id': ozon_product_id})
            
            _data = {
                'user_id': msg[0],
                'product_id': ozon_product_id,
                'product_marker': 'ozon_product',
                'job_id': job.id,
            }

            user_job = UserJob(**_data)

            session.add(user_job)

            try:
                await session.commit()
                _text = 'Ozon товар успешно добавлен'
                print(_text)
            except Exception as ex:
                print(ex)
                await session.rollback()
                _text = 'Ozon товар не был добавлен'
                print(_text)
            # else:

        except Exception as ex:
            print(ex)
            return True
        pass

## WB
    elif link.find('wildberries') > 0:
        # save wb product
        _prefix = 'catalog/'

        _idx_prefix = link.find(_prefix)

        short_link = link[_idx_prefix + len(_prefix):].split('/')[0]

        # data = await state.get_data()
        query = (
            select(
                WbProduct.id,
            )\
            .where(
                WbProduct.user_id == msg[0],
                WbProduct.link == link,
            )
        )
        async with session as _session:
            res = await _session.execute(query)

        res = res.scalar_one_or_none()

        if res:
            # await bot.send_message(chat_id=msg[0],
            #                        text='Товар уже добавлен')
            return True


        # msg: tuple = data.get('msg')

        query = (
            select(WbPunkt.zone)\
            .join(User,
                WbPunkt.user_id == User.tg_id)\
            .where(User.tg_id == msg[0])
        )
        async with session as session:
            res = await session.execute(query)

            del_zone = res.scalar_one_or_none()

        if not res:
            await bot.send_message(chat_id=msg[0],
                                   text='Не получилось найти пункт выдачи')
            return
        
        # query = (
        #     select(
        #         WbProduct.id
        #     )\
        #     .join(User,
        #         WbProduct.user_id == User.tg_id)\
        #     .where(
        #         and_(
        #             User.tg_id == msg[0],
        #             WbProduct.link == link,
        #         )
        #     )
        # )
        # async with session as session:
        #     res = await session.execute(query)

        #     check_product_by_user = res.scalar_one_or_none()

        # if check_product_by_user:
            # _kb = create_or_add_cancel_btn()
            # await bot.edit_message_text(chat_id=msg[0],
            #                             message_id=msg[-1],
            #                             text='Продукт уже добален',
            #                             reply_markup=_kb.as_markup())
            # await message.delete()
            # return
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession() as aiosession:
                _url = f"http://172.18.0.2:8080/product/{del_zone}/{short_link}"
                async with aiosession.get(url=_url,
                                timeout=timeout) as response:
                # response = await aiosession.get(url=_url)

                    try:
                        res = await response.json()
                        print(res)
                    except Exception as ex:
                        print('API RESPONSE ERROR', ex)
                        # await message.answer('ошибка при запросе к апи\n/start')
                        return
        except Exception as ex:
            print(ex)
            return True

        d = res.get('data')

        print(d.get('products')[0].get('sizes'))

        sizes = d.get('products')[0].get('sizes')

        _product_name = d.get('products')[0].get('name')

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

        async with session.begin():
            query = (
                select(WbPunkt.id,
                        WbPunkt.zone)\
                .join(User,
                        WbPunkt.user_id == User.tg_id)\
                .where(User.tg_id == msg[0])
            )

            _wb_punkt_id = await session.execute(query)

            _wb_punkt_id = _wb_punkt_id.fetchall()

            # print('short_link', data.get('wb_product_id'))
            _sale = generate_sale_for_price(float(_product_price))

            _data_name = _name if _name else _product_name

            if _wb_punkt_id:
                _wb_punkt_id, zone = _wb_punkt_id[0]
                _data = {
                    'link': link,
                    'short_link': short_link,
                    'start_price': _product_price,
                    'actual_price': _product_price,
                    #
                    'sale': _sale,
                    #
                    # 'percent': float(data.get('percent')),
                    'name': _data_name,
                    'time_create': datetime.now(),
                    'user_id': msg[0],
                    'wb_punkt_id': _wb_punkt_id,
                }

                # if percent:
                #     _data.update(percent=int(percent))

                wb_product = WbProduct(**_data)

                session.add(wb_product)

                await session.flush()

                wb_product_id = wb_product.id

                print('product_id', wb_product_id)
                
                # query = (
                #     insert(WbProduct)\
                #     .values(**data)
                # )
                # await session.execute(query)

                # try:
                #     await session.commit()
                # except Exception as ex:
                #     print(ex)
                # else:
                    # scheduler.add_job()
                #          user_id | marker | product_id
                job_id = f'{msg[0]}.wb.{wb_product_id}'
        
                job = scheduler.add_job(push_check_wb_price,
                                trigger='interval',
                                minutes=15,
                                id=job_id,
                                coalesce=True,
                                jobstore='sqlalchemy',
                                kwargs={'user_id': msg[0],
                                        'product_id': wb_product_id})
                
                _data = {
                    'user_id': msg[0],
                    'product_id': wb_product_id,
                    'product_marker': 'wb_product',
                    'job_id': job.id,
                }

                user_job = UserJob(**_data)

                session.add(user_job)

                try:
                    await session.commit()
                except Exception as ex:
                    print(ex)
                    _text = 'Что то пошло не так'
                else:
                    _text = 'Wb товар успешно добавлен'
                    print(_text)
            else:
                _text = 'Что то пошло не так'
                print(_text)


                    # await state.update_data(wb_product_link=wb_product_link,
                    #                         wb_product_id=wb_product_id,
                    #                         wb_start_price=float(_product_price),
                    #                         wb_product_price=float(_product_price),
                    #                         wb_product_name=_product_name)

        pass
    else:
        # error
        pass


    # if _idx > 0:
    #     link = message.text[_idx:]
    # else:
    #     return
    
    # if link.startswith('https://ozon'):
    #     query = (
    #         update(
    #             User
    #         )\
    #         .values(last_action_time=datetime.now(),
    #                 last_action='ozon')\
    #         .where(User.tg_id == message.from_user.id)
    #     )

    #     await session.execute(query)
    #     await session.commit()
    #     pass

# async def validate_link(message: types.Message,
#                         state: FSMContext,
#                         session: AsyncSession):
#     _idx = message.text.find('https')

#     if _idx > 0:
#         link = message.text[_idx:]
#     else:
#         return
    
#     if link.startswith('https://ozon'):
#         query = (
#             update(
#                 User
#             )\
#             .values(last_action_time=datetime.now(),
#                     last_action='ozon')\
#             .where(User.tg_id == message.from_user.id)
#         )

#         await session.execute(query)
#         await session.commit()
#         pass



        # ozon_link = message.text.strip()

        # query = (
        #     select(
        #         OzonProduct.id
        #     )\
        #     .join(User,
        #         OzonProduct.user_id == User.tg_id)\
        #     .where(
        #         and_(
        #             User.tg_id == message.from_user.id,
        #             OzonProduct.link == ozon_link,
        #         )
        #     )
        # )
        # async with session as session:
        #     res = await session.execute(query)

        #     check_product_by_user = res.scalar_one_or_none()

        # if check_product_by_user:
        #     # _kb = create_or_add_cancel_btn()
        #     # # await msg.edit_text(text='Продукт уже добален',
        #     # #                     reply_markup=_kb.as_markup())
        #     # await message.delete()
        #     return


        # # _kb = create_done_kb(marker='ozon_product')

        # # _kb = create_or_add_cancel_btn()


        # # await state.update_data(ozon_link=ozon_link)

        # if ozon_link.startswith('https://ozon.ru/t/'):
        #     _idx = ozon_link.find('/t/')
        #     print(_idx)
        #     _prefix = '/t/'
        #     ozon_short_link = 'croppedLink|' + ozon_link[_idx+len(_prefix):]
        #     print(ozon_short_link)
        # else:
        #     _prefix = 'product/'

        #     _idx = ozon_link.rfind('product/')

        #     ozon_short_link = ozon_link[(_idx + len(_prefix)):]

        # await state.update_data(ozon_short_link=ozon_short_link)

        # print('do request')

        # try:
        #     async with aiohttp.ClientSession() as aiosession:
        #         # _url = f"http://5.61.53.235:1441/product/{message.text}"
        #         _url = f"http://172.18.0.4:8080/product/{ozon_short_link}"

        #         response = await aiosession.get(url=_url)

        #         print(response.status)

        #         res = await response.text()

        #         # print(res)

        #         w = re.findall(r'\"cardPrice.*currency?', res)
        #         print(w)

        #         _alt = re.findall(r'\"alt.*,?', res)
        #         _product_name = None
        #         _product_name_limit = 21
                
        #         if _alt:
        #             _product_name = _alt[0].split('//')[0]
        #             _prefix = f'\"alt\":\"'
                    
        #             # if _product_name.startswith(_prefix):
        #             # _product_name = _product_name[len(_prefix)+2:][:_product_name_limit]
        #             _product_name = _product_name[len(_prefix)+2:]

        #         print(_product_name)

        #         await state.update_data(ozon_product_name=_product_name)
        #         # print('NAME   ',_alt[0].split('//')[0])

        #         if w:
        #             w = w[0].split(',')[:3]

        #             _d = {
        #                 'price': None,
        #                 'originalPrice': None,
        #                 'cardPrice': None,
        #             }

        #             for k in _d:
        #                 if not all(v for v in _d.values()):
        #                     for q in w:
        #                         if q.find(k) != -1:
        #                             name, price = q.split(':')
        #                             price = price.replace('\\', '').replace('"', '')
        #                             price = float(''.join(price.split()[:-1]))
        #                             print(price)
        #                             _d[k] = price
        #                             break
        #                 else:
        #                     break

        #             print(_d)

        #             await state.update_data(ozon_start_price=_d.get('cardPrice', 0))
        #             await state.update_data(ozon_actual_price=_d.get('cardPrice', 0))

        #             price_text = '|'.join(str(v) for v in _d.items())
        #         else:
        #             _text = 'Возникли проблемы'
            
        #     _product_price = _d.get('cardPrice')
        #     example_percent = 10
        #     example_different = (_product_price * example_percent) / 100
        #     example_price = _product_price - example_different

        #     _text = f'Основная цена товара: {_product_price}\nАктуальная цена товара: {_product_price}\nВведите <b>процент как число</b>.\nКогда цена товара снизится <b>на этот процент или ниже</b>, мы сообщим Вам.\n\nПример:\n   Процент: {example_percent}\n   Ожидаемая(или ниже) цена товара: {_product_price} - {example_different} = {example_price}'

        #     # _text = f'Ваш продукт\n{message.text}\nЦена продукта: {price_text}'

        #     await state.update_data(ozon_product=message.text)  # ?

        #     await state.set_state(OzonProduct.percent)

        #     if msg:
        #         await bot.edit_message_text(text=_text,
        #                                     chat_id=message.chat.id,
        #                                     message_id=msg.message_id,
        #                                     reply_markup=_kb.as_markup())
        #     else:
        #         await bot.send_message(chat_id=message.chat.id,
        #                             text=_text,
        #                             reply_markup=_kb.as_markup())
                
        #     await message.delete()
        # except Exception as ex:
        #     print(ex)
        #     pass
    # elif link.startswith('https://www.wildberries'):
    #     query = (
    #         update(
    #             User
    #         )\
    #         .values(lact_action_time=datetime.now(),
    #                 last_action='wb')\
    #         .where(User.tg_id == message.from_user.id)
    #     )

    #     await session.execute(query)
    #     await session.commit()
    #     pass
    # else:
    #     pass



async def clear_state_and_redirect_to_start(message: types.Message | types.CallbackQuery,
                                            state: FSMContext,
                                            bot: Bot):
    await state.clear()

    _kb = add_back_btn(InlineKeyboardBuilder())

    _text = 'Что то пошло не так\nВернитесь в главное меню и попробуйте еще раз'

    await bot.send_message(chat_id=message.from_user.id,
                           text=_text,
                           reply_markup=_kb.as_markup())


async def save_data_to_storage(callback: types.CallbackQuery,
                               state: FSMContext,
                               session: AsyncSession,
                               bot: Bot,
                               scheduler: AsyncIOScheduler,
                               callback_data: str):
    data = await state.get_data()

    async with session as session:
        match callback_data:
            case 'wb_punkt':
                list_punkt: list = data.get('list_punkt', list())

                lat = data.get('lat')
                lon = data.get('lon')
                del_zone = data.get('del_zone')

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

                await session.execute(query)

                try:
                    await session.commit()
                    _text = 'Wb пукнт успешно добавлен'
                except Exception:
                    await session.rollback()
                    _text = 'Wb пукнт не удалось добавить'

                if lat and lon:
                    list_punkt.append([lat, lon])
                    await state.update_data(list_punkt=list_punkt)

                    # _text = 'Wb пукнт успешно добавлен'
            case 'ozon_product':
                _data = {
                    'link': data.get('ozon_link'),
                    'short_link': data.get('ozon_short_link'),
                    'actual_price': data.get('ozon_actual_price'),
                    'start_price': data.get('ozon_start_price'),
                    'basic_price': data.get('ozon_basic_price'),
                    'sale': int(data.get('sale')),
                    'name': data.get('ozon_product_name'),
                    'time_create': datetime.now(),
                    'user_id': callback.from_user.id,
                }
                
                # query = (
                #     insert(OzonProduct)\
                #     .values(**_data)
                # )

                # await session.execute(query)
                ozon_product = OzonProduct(**_data)

                session.add(ozon_product)

                await session.flush()

                ozon_product_id = ozon_product.id

                #          user_id | marker | product_id
                job_id = f'{callback.from_user.id}.ozon.{ozon_product_id}'

                job = scheduler.add_job(push_check_ozon_price,
                                trigger='interval',
                                minutes=15,
                                id=job_id,
                                jobstore='sqlalchemy',
                                coalesce=True,
                                kwargs={'user_id': callback.from_user.id,
                                        'product_id': ozon_product_id})
                
                _data = {
                    'user_id': callback.from_user.id,
                    'product_id': ozon_product_id,
                    'product_marker': 'ozon_product',
                    'job_id': job.id,
                }

                user_job = UserJob(**_data)

                session.add(user_job)

                try:
                    await session.commit()
                    _text = 'Ozon товар успешно добавлен'
                except Exception as ex:
                    print(ex)
                    await session.rollback()
                    _text = 'Ozon товар не был добавлен'
                pass
            case 'wb_product':
            # if _basic_price and _product_price:

                async with session.begin():
                    query = (
                        select(WbPunkt.id,
                               WbPunkt.zone)\
                        .join(User,
                                WbPunkt.user_id == User.tg_id)\
                        .where(User.tg_id == callback.from_user.id)
                    )

                    _wb_punkt_id = await session.execute(query)

                    _wb_punkt_id = _wb_punkt_id.fetchall()

                    print('short_link', data.get('wb_product_id'))

                    if _wb_punkt_id:
                        _wb_punkt_id, zone = _wb_punkt_id[0]
                        _data = {
                            'link': data.get('wb_product_link'),
                            'short_link': data.get('wb_product_id'),
                            'start_price': data.get('wb_start_price'),
                            'actual_price': data.get('wb_product_price'),
                            'sale': float(data.get('sale')),
                            'name': data.get('wb_product_name'),
                            'time_create': datetime.now(),
                            'user_id': callback.from_user.id,
                            'wb_punkt_id': _wb_punkt_id,
                        }

                        wb_product = WbProduct(**_data)

                        session.add(wb_product)

                        await session.flush()

                        wb_product_id = wb_product.id

                        print('product_id', wb_product_id)
                        
                        # query = (
                        #     insert(WbProduct)\
                        #     .values(**data)
                        # )
                        # await session.execute(query)

                        # try:
                        #     await session.commit()
                        # except Exception as ex:
                        #     print(ex)
                        # else:
                            # scheduler.add_job()
                        #          user_id | marker | product_id
                        job_id = f'{callback.from_user.id}.wb.{wb_product_id}'

                        job = scheduler.add_job(push_check_wb_price,
                                        trigger='interval',
                                        minutes=15,
                                        id=job_id,
                                        coalesce=True,
                                        jobstore='sqlalchemy',
                                        kwargs={'user_id': callback.from_user.id,
                                                'product_id': wb_product_id})
                        
                        _data = {
                            'user_id': callback.from_user.id,
                            'product_id': wb_product_id,
                            'product_marker': 'wb_product',
                            'job_id': job.id,
                        }

                        user_job = UserJob(**_data)

                        session.add(user_job)

                        try:
                            await session.commit()
                        except Exception as ex:
                            print(ex)
                            _text = 'Что то пошло не так'
                        else:
                            _text = 'Wb товар успешно добавлен'
                    else:
                        _text = 'Что то пошло не так'

    return _text


async def add_user(message: types.Message,
                   session: AsyncSession):
    data = {
        'tg_id': message.from_user.id,
        'username': message.from_user.username,
        'first_name': message.from_user.first_name,
        'last_name': message.from_user.last_name,
        'time_create': datetime.now(),
    }

    query = (
        insert(
            User
        )\
        .values(**data)
    )
    async with session as _session:
        try:
            await _session.execute(query)
            await _session.commit()
        except Exception as ex:
            print(ex)
            await _session.rollback()
        else:
            print('user added')
            return True


async def check_user(message: types.Message,
                     session: AsyncSession):
    async with session as _session:
        query = (
            select(User)\
            .where(User.tg_id == message.from_user.id)
        )
        # async with session as session:
        res = await _session.execute(query)

        res = res.scalar_one_or_none()

    if res:
        return True
    else:
        return await add_user(message,
                                session)



async def show_item(callback: types.CallbackQuery,
                    state: FSMContext):
    data = await state.get_data()

    marker = data.get('action')

    msg: types.Message = data.get('msg')
    product_id, link, actaul_price, start_price, user_id, time_create, percent, job_id, photo_kb = item_constructor(data)

    # if not data.get('visited'):
    #     await state.update_data(visited=True)
    time_create: datetime
    moscow_tz = pytz.timezone('Europe/Moscow')
    moscow_time = time_create.astimezone(moscow_tz)

    waiting_price = actaul_price - ((actaul_price * percent) / 100)

    _text = f'Привет {user_id}\nТвой {marker} <a href="{link}">товар</a>\n\nНачальная цена: {start_price}\nАктуальная цена: {actaul_price}\nВыставленный процент: {percent}\nОжидаемая(или ниже) цена товара:{waiting_price}\nДата начала отслеживания: {moscow_time}'

    _kb = add_cancel_btn_to_photo_keyboard(photo_kb)

    _kb = create_remove_kb(user_id=callback.from_user.id,
                           product_id=product_id,
                           marker=marker,
                           job_id=job_id,
                           _kb=_kb)
    # _kb = create_or_add_cancel_btn(_kb)

    if msg:
        await msg.edit_text(text=_text,
                            reply_markup=_kb.as_markup())

    # await callback.message.answer_photo(photo,
    #                                     caption=f'Товар: {name}\nЦена: {price}',
    #                                     reply_markup=photo_kb.as_markup())
        
    # else:
    #     await callback.message.edit_media(InputMediaPhoto(media=photo,
    #                                                       type='photo',
    #                                                       caption=f'Товар: {name}\nЦена: {price}'),
    #                                       reply_markup=photo_kb.as_markup())
        

def item_constructor(data: dict[str, Any]):
    marker = data.get('action')

    product_idx = data.get(f'{marker}_product_idx')
    product_list = data.get(f'{marker}_product_list')

    # product_idx = data['_idx_product']
    # wb_product_list = data['wb_product_list']
    print(f'{marker}_product list', product_list, 'idx', product_idx)
    kb_init: str
    
    if len(product_list) == 1:
        kb_init = 'one'
    else:
        if product_idx == 0:
            kb_init = 'start'
        elif product_idx < len(product_list)-1:
            kb_init = 'mid'
        else:
            kb_init = 'end'

    photo_kb = create_photo_keyboard(kb_init)
    _product = product_list[product_idx]
    # name = data['name']
    # price = data['price']
    product_id, link, actaul_price, start_price, user_id, time_create, sale, job_id = _product

    return (
        product_id,
        link,
        actaul_price,
        start_price,
        user_id,
        time_create,
        sale,
        job_id,
        photo_kb,
    )



async def show_item_list(callback: types.CallbackQuery,
                         state: FSMContext,
                         bot: Bot):
    data = await state.get_data()

    marker = data.get('action')

    msg: tuple = data.get('msg')

    # product_idx = data.get(f'{marker}_product_idx')
    product_list = data.get(f'{marker}_product_list')

    _kb = create_product_list_kb(callback.from_user.id,
                                 product_list,
                                 marker)
    _kb = create_or_add_cancel_btn(_kb)
    
    _text = f'Ваши {marker} товары'
    
    if msg:
        await bot.edit_message_text(chat_id=msg[0],
                                    message_id=msg[-1],
                                    text=_text,
                                    reply_markup=_kb.as_markup())
    else:
        await bot.send_message(chat_id=callback.from_user.id,
                               text=_text,
                               reply_markup=_kb.as_markup())
    



async def show_product_list(product_dict: dict,
                            user_id: int,
                            state: FSMContext):
    data = await state.get_data()

    print('data' ,data)

    current_page = product_dict.get('current_page')
    product_list = product_dict.get('product_list')
    len_product_list = product_dict.get('len_product_list')

    list_msg: tuple = data.get('list_msg')

    # view_product_dict = {
    #     'len_product_list': len_product_list,
    #     'pages': pages,
    #     'current_page': current_page,
    #     'product_list': product_list,
    # }

    start_idx = (current_page - 1) * DEFAULT_PAGE_ELEMENT_COUNT
    end_idx = current_page * DEFAULT_PAGE_ELEMENT_COUNT

    product_list_for_page = product_list[start_idx:end_idx]

    _kb = create_product_list_for_page_kb(product_list_for_page)
    _kb = add_pagination_btn(_kb,
                             product_dict)
    _kb = create_or_add_exit_btn(_kb)

    product_on_current_page_count = len(product_list_for_page)

    _text = f'Ваши товары\n\nВсего товаров: {len_product_list}\nПоказано {product_on_current_page_count} товар(a/ов)'

    if not list_msg:
        list_msg = await bot.send_message(chat_id=user_id,
                            text=_text,
                            reply_markup=_kb.as_markup())
        
        await state.update_data(list_msg=(list_msg.chat.id, list_msg.message_id),
                                view_product_dict=product_dict)
    else:
        await bot.edit_message_text(chat_id=user_id,
                                    message_id=list_msg[-1],
                                    text=_text,
                                    reply_markup=_kb.as_markup())
    # for product in product_list_for_page:
    #     product_id, link, actual, start, user_id, _date, marker, name, sale, job_id = product
    
    pass