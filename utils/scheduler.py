import json
import re
import pytz
import aiohttp
import asyncio
import aiofiles
import base64

from math import ceil
from datetime import datetime, timedelta
from typing import Literal

from aiogram import types, Bot

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.job import Job

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import insert, select, and_, update, func, desc

from db.base import (OzonPunkt, Product, Punkt,
                     Subscription,
                     WbProduct,
                     WbPunkt,
                     User,
                     get_session,
                     UserJob,
                     OzonProduct,
                     UTM,
                     UserProduct,
                     UserProductJob,
                     ProductPrice)

from keyboards import (add_graphic_btn, add_or_create_close_kb,
                       create_remove_and_edit_sale_kb,
                       create_remove_kb, new_create_remove_and_edit_sale_kb)

from bot22 import bot

from .storage import redis_client
from .any import (generate_pretty_amount,
                  generate_sale_for_price,
                  add_message_to_delete_dict,
                  send_data_to_yandex_metica)
from .pics import DEFAULT_PRODUCT_LIST_PHOTO_ID, DEFAULT_PRODUCT_PHOTO_ID
from .cities import city_index_dict
from .exc import OzonAPICrashError, OzonProductExistsError, WbAPICrashError, WbProductExistsError

from config import DEV_ID, SUB_DEV_ID, WB_API_URL, OZON_API_URL, JOB_STORE_URL, TEST_PHOTO_ID


# Настройка хранилища задач
jobstores = {
    'sqlalchemy': SQLAlchemyJobStore(url=JOB_STORE_URL),
}

# Создание и настройка планировщика
scheduler = AsyncIOScheduler(jobstores=jobstores)


timezone = pytz.timezone('Europe/Moscow')

scheduler_cron = CronTrigger(minute=1,
                             timezone=timezone)

scheduler_interval = IntervalTrigger(hours=1,
                                     timezone=timezone)


async def add_task_to_delete_old_message_for_users(user_id: int = None):
    print('add task to delete old message...')

    async for session in get_session():
        try:
            if user_id is not None:
                query = (
                    select(
                        User.tg_id,
                    )\
                    .where(
                        User.tg_id == user_id,
                    )
                    )
            else:
                query = (
                    select(
                        User.tg_id,
                        )
                    )

            res = await session.execute(query)

            res = res.fetchall()
        finally:
            try:
                await session.close()
            except Exception:
                pass

    for user in res:
        user_id = user[0]
        job_id = f'delete_msg_task_{user_id}'

        scheduler.add_job(periodic_delete_old_message,
                          trigger=scheduler_interval,
                          id=job_id,
                          jobstore='sqlalchemy',
                          coalesce=True,
                          kwargs={'user_id': user_id})


async def periodic_delete_old_message(user_id: int):
    print(f'TEST SCHEDULER TASK DELETE OLD MESSAGE USER {user_id}')
    key = f'fsm:{user_id}:{user_id}:data'

    async with redis_client.pipeline(transaction=True) as pipe:
        user_data: bytes = await pipe.get(key)
        results = await pipe.execute()
        #Извлекаем результат из выполненного pipeline
    # print('RESULTS', results)
    # print('USER DATA (BYTES)', user_data)

    json_user_data: dict = json.loads(results[0])
    # print('USER DATA', json_user_data)

    dict_msg_on_delete: dict = json_user_data.get('dict_msg_on_delete')

    if dict_msg_on_delete:
        for _key in list(dict_msg_on_delete.keys()):
            chat_id, message_date = dict_msg_on_delete.get(_key)
            date_now = datetime.now()
            # тестовый вариант, удаляем сообщения старше 1 часа
            print((datetime.fromtimestamp(date_now.timestamp()) - datetime.fromtimestamp(message_date)) > timedelta(hours=36))
            if (datetime.fromtimestamp(date_now.timestamp()) - datetime.fromtimestamp(message_date)) > timedelta(hours=36):
                try:
                    await bot.delete_message(chat_id=chat_id,
                                            message_id=_key)
                    await asyncio.sleep(0.1)
                    # await bot.delete_messages() # что будет если какое то сообщение не сможет удалиться и произойдет ошибка ???
                except Exception as ex:
                    del dict_msg_on_delete[_key]
                    print(ex)
                else:
                    del dict_msg_on_delete[_key]

    pass


async def test_periodic_delete_old_message(user_id: int):
    print(f'TEST SCHEDULER TASK DELETE OLD MESSAGE USER {user_id}')
    key = f'fsm:{user_id}:{user_id}:data'

    async with redis_client.pipeline(transaction=True) as pipe:
        user_data: bytes = await pipe.get(key)
        results = await pipe.execute()
        #Извлекаем результат из выполненного pipeline
    # print('RESULTS', results)
    # print('USER DATA (BYTES)', user_data)


    if results[0] is not None:
        json_user_data: dict = json.loads(results[0])
        # print('USER DATA', json_user_data)

        dict_msg_on_delete: dict = json_user_data.get('dict_msg_on_delete')

        message_id_on_delete_list = []

        if dict_msg_on_delete:
            for _key in list(dict_msg_on_delete.keys()):
                chat_id, message_date = dict_msg_on_delete.get(_key)
                date_now = datetime.now()
                # тестовый вариант, удаляем сообщения старше 1 часа
                print((datetime.fromtimestamp(date_now.timestamp()) - datetime.fromtimestamp(message_date)) > timedelta(hours=36))
                if (datetime.fromtimestamp(date_now.timestamp()) - datetime.fromtimestamp(message_date)) > timedelta(hours=36):
                    message_id_on_delete_list.append(_key)
                    # try:
                    #     await bot.delete_message(chat_id=chat_id,
                    #                             message_id=_key)
                    #     await asyncio.sleep(0.1)
                    #     # await bot.delete_messages() # что будет если какое то сообщение не сможет удалиться и произойдет ошибка ???
                    # except Exception as ex:
                    #     del dict_msg_on_delete[_key]
                    #     print(ex)
                    # else:
                    del dict_msg_on_delete[_key]

        # ?
        # json_user_data['dict_msg_on_delete'] = dict_msg_on_delete

        async with redis_client.pipeline(transaction=True) as pipe:
            bytes_data = json.dumps(json_user_data)
            await pipe.set(key, bytes_data)
            results = await pipe.execute()

        if message_id_on_delete_list:
            iterator_count = ceil(len(message_id_on_delete_list) / 100)

            for i in range(iterator_count):
                idx = i * 100
                _messages_on_delete = message_id_on_delete_list[idx:idx+100]
                
                await bot.delete_messages(chat_id=chat_id,
                                        message_ids=_messages_on_delete)
                await asyncio.sleep(0.2)
        pass




async def check_product_by_user_in_db(user_id: int,
                                      short_link: str,
                                      marker: Literal['wb', 'ozon'],
                                      session: AsyncSession):
    product_model = OzonProduct if marker == 'ozon' else WbProduct

    query = (
        select(
            product_model.id
        )\
        .where(
            and_(
                product_model.short_link == short_link,
                product_model.user_id == user_id,
            )
        )
    )
    async with session as _session:
        res = await _session.execute(query)
    
    _check_product = res.scalar_one_or_none()

    return bool(_check_product)


async def new_check_product_by_user_in_db(user_id: int,
                                          short_link: str,
                                          session: AsyncSession):
    query = (
        select(
            UserProduct.id
        )\
        .join(Product,
              UserProduct.product_id == Product.id)
        .where(
            and_(
                Product.short_link == short_link,
                UserProduct.user_id == user_id,
            )
        )
    )
    async with session as _session:
        res = await _session.execute(query)
    
    _check_product = res.scalar_one_or_none()

    return bool(_check_product)


async def check_subscription_limit(user_id: int,
                                   marker: Literal['wb', 'ozon'],
                                   session: AsyncSession):
    # product_model = OzonProduct if marker == 'ozon' else WbProduct
    print(marker)
    marker = marker.lower()

    if marker == 'ozon':
        product_model = OzonProduct

        query = (
            select(
                func.count(product_model.id),
                Subscription.ozon_product_limit,
            )\
            .join(User,
                product_model.user_id == User.tg_id)\
            .join(Subscription,
                User.subscription_id == Subscription.id)
            .where(
                and_(
                    # product_model.short_link == short_link,
                    product_model.user_id == user_id,
                )
            )\
            .group_by(Subscription.ozon_product_limit)
        )
    else:
        product_model = WbProduct
        query = (
            select(
                func.count(product_model.id),
                Subscription.wb_product_limit,
            )\
            .join(User,
                product_model.user_id == User.tg_id)\
            .join(Subscription,
                User.subscription_id == Subscription.id)
            .where(
                and_(
                    # product_model.short_link == short_link,
                    product_model.user_id == user_id,
                )
            )\
            .group_by(Subscription.wb_product_limit)
        )

    async with session as _session:
        res = await _session.execute(query)
    
    _check_limit = res.fetchall()

    if _check_limit:
        _check_limit = _check_limit[0]

        product_count, subscription_limit = _check_limit

        print('SUBSCRIPTION TEST', product_count, subscription_limit)

        if product_count >= subscription_limit:
            return subscription_limit


async def new_check_subscription_limit(user_id: int,
                                       marker: Literal['wb', 'ozon'],
                                       session: AsyncSession):
    # product_model = OzonProduct if marker == 'ozon' else WbProduct
    # print(marker)
    marker = marker.lower()

    if marker == 'wb':
        subscription_limit = Subscription.wb_product_limit
    else:
        subscription_limit = Subscription.ozon_product_limit


    query = (
        select(
            func.count(UserProduct.id),
            subscription_limit,
        )\
        .join(User,
              UserProduct.user_id == User.tg_id)\
        .join(Subscription,
              User.subscription_id == Subscription.id)\
        .join(Product,
              UserProduct.product_id == Product.id)\
        .where(
            and_(
                # product_model.short_link == short_link,
                Product.product_marker == marker,
                UserProduct.user_id == user_id,
            )
        )\
        .group_by(subscription_limit)
    )
    # else:
    #     product_model = WbProduct
    #     query = (
    #         select(
    #             func.count(product_model.id),
    #             Subscription.wb_product_limit,
    #         )\
    #         .join(User,
    #             product_model.user_id == User.tg_id)\
    #         .join(Subscription,
    #             User.subscription_id == Subscription.id)
    #         .where(
    #             and_(
    #                 # product_model.short_link == short_link,
    #                 product_model.user_id == user_id,
    #             )
    #         )\
    #         .group_by(Subscription.wb_product_limit)
    #     )

    async with session as _session:
        res = await _session.execute(query)
    
    _check_limit = res.fetchall()

    if _check_limit:
        _check_limit = _check_limit[0]

        product_count, subscription_limit = _check_limit

        print('SUBSCRIPTION TEST', product_count, subscription_limit)

        if product_count >= subscription_limit:
            return subscription_limit


async def save_product(user_data: dict,
                       session: AsyncSession,
                       scheduler: AsyncIOScheduler,
                       percent: str = None):
    msg = user_data.get('msg')
    _name = user_data.get('name')
    link: str = user_data.get('link')
    link = link.split('?')[0]
    # percent: int = user_data.get('percent')

    ozon_query = (
        select(OzonProduct.id)\
        .where(OzonProduct.user_id == msg[0])
    )

    wb_query = (
        select(WbProduct.id)\
        .where(WbProduct.user_id == msg[0])
    )

    async with session as _session:
        res = await _session.execute(ozon_query.union(wb_query))

    products_by_user = res.scalars().all()

    product_count_by_user = len(products_by_user)

    is_first_product = not bool(product_count_by_user)

    print(f'PRODUCT COUNT BY USER {msg[0]} {product_count_by_user}')

    # if product_count_by_user >= 100:
    #     return True

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
        
        query = (
            select(
                OzonPunkt.id,
                OzonPunkt.zone,
                )\
            .join(User,
                  OzonPunkt.user_id == User.tg_id)\
            .where(User.tg_id == msg[0])
        )
        async with session as _session:
            res = await _session.execute(query)

            _ozon_punkt = res.fetchall()

        if _ozon_punkt:
            ozon_punkt_id, del_zone = _ozon_punkt[0]
        else:
            ozon_punkt_id, del_zone = (None, None)

        print('do request on OZON API')

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession() as aiosession:
                # _url = f"http://5.61.53.235:1441/product/{message.text}"
                if not del_zone:
                    _url = f"http://172.18.0.6:8080/product/{ozon_short_link}"
                else:
                    _url = f"http://172.18.0.6:8080/product/{del_zone}/{ozon_short_link}"

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

            check_product_by_user =  await check_product_by_user_in_db(user_id=msg[0],
                                                                       short_link=_new_short_link,
                                                                       marker='ozon',
                                                                       session=session)

            if check_product_by_user:
                return True

            response_data = res.split('|')[-1]
            json_data: dict = json.loads(response_data)

            w = re.findall(r'\"cardPrice.*currency?', res)
            # print(w)

            # _alt = re.findall(r'\"alt.*,?', res)
            _product_name = None
            _product_name_limit = 21
            
            # if _alt:
            #     _product_name = _alt[0].split('//')[0]
            #     _prefix = f'\"alt\":\"'
                
            #     # if _product_name.startswith(_prefix):
            #     # _product_name = _product_name[len(_prefix)+2:][:_product_name_limit]
            #     _product_name = _product_name[len(_prefix)+2:]
            #     _product_name = ' '.join(_product_name.split()[:4])

            # print(_product_name)

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
                # print('22')
                try:
                    # response_data = res.split('|')[-1]

                    # json_data: dict = json.loads(response_data)

                    # _name = ' '.join(json_data.get('seo').get('title').split()[:4])

                    script_list = json_data.get('seo').get('script')

                    # if v:
                    #     t = v.get('script')

                    # if script_list:
                    inner_html = script_list[0].get('innerHTML') #.get('offers').get('price')

                    # print('innerHTML', inner_html)

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
                        print('problem', ex)
                        return True

                    # print('PRICE PARSE ERROR', user_data)
                except Exception as ex:
                    print(ex)
                    return True
                
            _name = ' '.join(json_data.get('seo').get('title').split()[:4])
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
                'ozon_punkt_id': ozon_punkt_id,
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

            # async for session in get_session():
            async with session as _session:
                try:
                    await _session.commit()
                    _text = 'Ozon товар успешно добавлен'
                    print(_text)
                except Exception as ex:
                    print(ex)
                    await _session.rollback()
                    _text = 'Ozon товар не был добавлен'
                    print(_text)
                else:
                    if is_first_product:
                        # get request to yandex metrika
                        utm_query = (
                            select(
                                UTM.client_id
                            )\
                            .where(
                                UTM.user_id == int(msg[0])
                            )
                        )

                        utm_res = await _session.execute(utm_query)

                        client_id = utm_res.scalar_one_or_none()

                        if client_id:
                            await send_data_to_yandex_metica(client_id,
                                                            goal_id='add_product')

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
            return True

        query = (
            select(
                WbPunkt.id,
                WbPunkt.zone,
                )\
            .join(User,
                WbPunkt.user_id == User.tg_id)\
            .where(User.tg_id == msg[0])
        )
        async with session as _session:
            res = await _session.execute(query)

            _wb_punkt = res.fetchall()

        if _wb_punkt:
            wb_punkt_id, del_zone = _wb_punkt[0]
        else:
            wb_punkt_id, del_zone = (None, -1281648)

        # if not del_zone:
        #     # lat, lon = ('55.707106', '37.572854')
        #     del_zone = -1281648

            # async with aiohttp.ClientSession() as aiosession:
            #     # _url = f"http://172.18.0.7:8080/pickUpPoint/{lat}/{lon}"
            #     # response = await aiosession.get(url=_url)

            #     # res = await response.json()

            #     # deliveryRegions = res.get('deliveryRegions')

            #     # print(deliveryRegions)

            #     # del_zone = deliveryRegions[-1]
            
            #     _data = {
            #         'lat': float(lat),
            #         'lon': float(lon),
            #         'zone': del_zone,
            #         'user_id': msg[0],
            #         'time_create': datetime.now(tz=pytz.timezone('Europe/Moscow')),
            #     }

            #     query = (
            #         insert(WbPunkt)\
            #         .values(**_data)
            #     )
            #     async with session as session:
            #         await session.execute(query)

            #         try:
            #             await session.commit()
            #             _text = 'Wb пукнт успешно добавлен'
            #         except Exception:
            #             await session.rollback()
            #             _text = 'Wb пукнт не удалось добавить'

            #             await bot.send_message(chat_id=msg[0],
            #                                 text='Не получилось найти пункт выдачи')
            #             return True
        
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
        check_product_by_user =  await check_product_by_user_in_db(user_id=msg[0],
                                                                    short_link=short_link,
                                                                    marker='wb',
                                                                    session=session)

        if check_product_by_user:
            return True

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession() as aiosession:
                _url = f"http://172.18.0.7:8080/product/{del_zone}/{short_link}"
                async with aiosession.get(url=_url,
                                timeout=timeout) as response:
                # response = await aiosession.get(url=_url)

                    try:
                        res = await response.json()
                        # print(res)
                    except Exception as ex:
                        print('API RESPONSE ERROR', ex)
                        # await message.answer('ошибка при запросе к апи\n/start')
                        return True
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

        async with session as _session:
            # async with _session.begin():
                # query = (
                #     select(WbPunkt.id,
                #             WbPunkt.zone)\
                #     .join(User,
                #             WbPunkt.user_id == User.tg_id)\
                #     .where(User.tg_id == msg[0])
                # )

                # _wb_punkt_id = await session.execute(query)

                # _wb_punkt_id = _wb_punkt_id.fetchall()

                # print('short_link', data.get('wb_product_id'))
                _sale = generate_sale_for_price(float(_product_price))

                _data_name = _name if _name else _product_name

                # if _wb_punkt_id:
                    # _wb_punkt_id, zone = _wb_punkt_id[0]
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
                    'wb_punkt_id': wb_punkt_id,
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
                    await _session.commit()
                except Exception as ex:
                    print(ex)
                    _text = 'Что то пошло не так'
                    return True
                # else:
        _text = 'Wb товар успешно добавлен'
        print(_text)

        if is_first_product:
            # get request to yandex metrika
            utm_query = (
                select(
                    UTM.client_id
                )\
                .where(
                    UTM.user_id == int(msg[0])
                )
            )

            async with session as _session:
                utm_res = await _session.execute(utm_query)

                client_id = utm_res.scalar_one_or_none()

                if client_id:
                    await send_data_to_yandex_metica(client_id,
                                                    goal_id='add_product')
                # else:
            #     _text = 'Что то пошло не так'
            #     print(_text)
            #     return True


                    # await state.update_data(wb_product_link=wb_product_link,
                    #                         wb_product_id=wb_product_id,
                    #                         wb_start_price=float(_product_price),
                    #                         wb_product_price=float(_product_price),
                    #                         wb_product_name=_product_name)

        pass
    else:
        # error
        pass


async def add_product_to_db(data: dict,
                            marker: str,
                            is_first_product: bool,
                            session: AsyncSession):
    short_link = data.get('short_link')
    name = data.get('name')
    user_id = data.get('user_id')
    photo_id = data.get('photo_id')

    check_product_query = (
        select(
            Product
        )\
        .where(
            Product.short_link == short_link,
        )
    )

    async with session as _session:
        res = await _session.execute(check_product_query)

    _product = res.scalar_one_or_none()

    if not _product:
        insert_data = {
            'product_marker': marker,
            'name': name,
            'short_link': short_link,
            'photo_id': photo_id,
        }

        _product = Product(**insert_data)
        _session.add(_product)

        await session.flush()
    
    product_id = _product.id

    user_product_data = {
        'link': data.get('link'),
        'product_id': product_id,
        'user_id': user_id,
        'start_price': data.get('start_price'),
        'actual_price': data.get('actual_price'),
        'sale': data.get('sale'),
        'time_create': datetime.now(),
    }

    user_product = UserProduct(**user_product_data)

    session.add(user_product)

    await session.flush()

    user_product_id = user_product.id

    #          user_id | marker | product_id
    job_id = f'{user_id}:{marker}:{user_product_id}'
    # job_id = 'test_job_id'

    if marker == 'wb':
        scheduler_func = new_push_check_wb_price
    else:
        scheduler_func = new_push_check_ozon_price

    job = scheduler.add_job(scheduler_func,
                            trigger='interval',
                            minutes=15,
                            id=job_id,
                            jobstore='sqlalchemy',
                            coalesce=True,
                            kwargs={'user_id': user_id,
                                    'product_id': user_product_id})
    
    _data = {
        'user_product_id': user_product_id,
        'job_id': job.id,
        # 'job_id': job_id,
    }

    user_job = UserProductJob(**_data)

    session.add(user_job)

    async with session as _session:
        try:
            await _session.commit()
            _text = f'{marker} товар успешно добавлен'
            print(_text)
        except Exception as ex:
            print(ex)
            await _session.rollback()
            _text = f'{marker} товар не был добавлен'
            print(_text)
        else:
            if is_first_product:
                # get request to yandex metrika
                utm_query = (
                    select(
                        UTM.client_id
                    )\
                    .where(
                        UTM.user_id == int(user_id)
                    )
                )

                utm_res = await _session.execute(utm_query)

                client_id = utm_res.scalar_one_or_none()

                if client_id:
                    await send_data_to_yandex_metica(client_id,
                                                     goal_id='add_product')


async def try_update_ozon_product_photo(product_id: int,
                                        short_link: str,
                                        session: AsyncSession):
    timeout = aiohttp.ClientTimeout(total=35)
    async with aiohttp.ClientSession() as aiosession:
        # _url = f"http://5.61.53.235:1441/product/{message.text}"
        # if not del_zone:
        _url = f"http://5.61.53.235:1441/product/{short_link}"
            # _url = f"{OZON_API_URL}/product/{ozon_short_link}"
        # else:
        #     _url = f"http://5.61.53.235:1441/product/{del_zone}/{ozon_short_link}"
            # _url = f"{OZON_API_URL}/product/{del_zone}/{ozon_short_link}"

        async with aiosession.get(url=_url,
                                    timeout=timeout) as response:
            _status_code = response.status
            print(f'OZON RESPONSE CODE {_status_code}')

            text_data = await response.text()

    
    photo_url_pattern = r'images\\":\[{\\"src\\":\\"https:\/\/cdn1\.ozone\.ru\/s3\/multimedia-[a-z0-9]*(-\w*)?\/\d+\.jpg'
    
    match = re.search(photo_url_pattern, text_data)

    if match:
        # print('search',match.group())
        photo_url_match = re.search(r'https.*\.jpg?', match.group())
        if photo_url_match:
            photo_url = photo_url_match.group()
            # print('RESULT URL',photo_url)

            api_check_id_channel = -1002558196527

            photo_msg = await bot.send_photo(chat_id=api_check_id_channel,
                                             photo=types.URLInputFile(url=photo_url))
            _photo = photo_msg.photo
            
            if _photo:
                photo_id = _photo[0].file_id
    else:
        # photo_id = TEST_PHOTO_ID
        photo_id = DEFAULT_PRODUCT_PHOTO_ID

    update_query = (
        update(
            Product
        )\
        .values(photo_id=photo_id)\
        .where(
            Product.id == product_id
        )
    )

    await session.execute(update_query)


async def try_get_ozon_product_photo(short_link: str,
                                     text_data: str,
                                     session: AsyncSession):
    check_query = (
        select(
            Product.photo_id,
        )\
        .where(
            Product.short_link == short_link,
        )
    )

    async with session as _session:
        res = await _session.execute(check_query)

    product_photo = res.scalar_one_or_none()

    if product_photo:
        return product_photo

    # photo_url_pattern = r'image\\":\\"https:\/\/cdn1\.ozone\.ru\/s3\/multimedia-\d+(-\w+)?\/\d+\.jpg'

    photo_url_pattern = r'images\\":\[{\\"src\\":\\"https:\/\/cdn1\.ozone\.ru\/s3\/multimedia-[a-z0-9]*(-\w*)?\/\d+\.jpg'
    
    match = re.search(photo_url_pattern, text_data)

    if match:
        # print('search',match.group())
        photo_url_match = re.search(r'https.*\.jpg?', match.group())
        if photo_url_match:
            photo_url = photo_url_match.group()
            # print('RESULT URL',photo_url)

            api_check_id_channel = -1002558196527

            photo_msg = await bot.send_photo(chat_id=api_check_id_channel,
                                             photo=types.URLInputFile(url=photo_url))
            _photo = photo_msg.photo
            
            if _photo:
                photo_id = _photo[0].file_id

                return photo_id
                # print('PHOTO ID',photo_id)
            
            # await bot.delete_message(chat_id=user_id,
            #                          message_id=photo_msg.message_id)
    else:
        print("URL не найден")


async def save_ozon_product(user_id: int,
                            link: str,
                            name: str | None,
                            is_first_product: bool,
                            session: AsyncSession):
    if link.startswith('https://ozon.ru/t/'):
        _idx = link.find('/t/')
        _prefix = '/t/'
        ozon_short_link = 'croppedLink|' + link[_idx+len(_prefix):]
        print(ozon_short_link)
    else:
        _prefix = 'product/'
        _idx = link.rfind('product/')
        ozon_short_link = link[(_idx + len(_prefix)):]

    query = (
        select(
            UserProduct.id,
        )\
        .where(
            UserProduct.user_id == user_id,
            UserProduct.link == link,
        )
    )
    async with session as _session:
        res = await _session.execute(query)

    res = res.scalar_one_or_none()

    if res:
        raise OzonProductExistsError()

    query = (
        select(
            Punkt.ozon_zone,
            )\
        .join(User,
              Punkt.user_id == User.tg_id)\
        .where(User.tg_id == user_id)
    )
    async with session as _session:
        res = await _session.execute(query)

    del_zone = res.scalar_one_or_none()

    print('do request on OZON API (new version)')

    # try:
    timeout = aiohttp.ClientTimeout(total=35)
    async with aiohttp.ClientSession() as aiosession:
        # _url = f"http://5.61.53.235:1441/product/{message.text}"
        if not del_zone:
            _url = f"http://5.61.53.235:1441/product/{ozon_short_link}"
            # _url = f"{OZON_API_URL}/product/{ozon_short_link}"
        else:
            _url = f"http://5.61.53.235:1441/product/{del_zone}/{ozon_short_link}"
            # _url = f"{OZON_API_URL}/product/{del_zone}/{ozon_short_link}"

        async with aiosession.get(url=_url,
                                    timeout=timeout) as response:
            _status_code = response.status
            print(f'OZON RESPONSE CODE {_status_code}')

            res = await response.text()

    if _status_code == 404 or res == '408 Request Timeout':
        raise OzonAPICrashError()

    _new_short_link = res.split('|')[0]

    check_product_by_user =  await new_check_product_by_user_in_db(user_id=user_id,
                                                                short_link=_new_short_link,
                                                                session=session)

    if check_product_by_user:
        raise OzonProductExistsError()

    response_data = res.split('|')[-1]
    json_data: dict = json.loads(response_data)

    photo_id = await try_get_ozon_product_photo(short_link=_new_short_link,
                                                text_data=res,
                                                session=session)

    if not photo_id:
        print('Не удалось спарсить фото OZON товара')
        raise Exception()

    w = re.findall(r'\"cardPrice.*currency?', res)

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
                        _name, price = q.split(':')
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

    else:
        # try:
            script_list = json_data.get('seo').get('script')

            inner_html = script_list[0].get('innerHTML') #.get('offers').get('price')

            # try:
            inner_html_json: dict = json.loads(inner_html)
            offers = inner_html_json.get('offers')

            _price = offers.get('price')

            start_price = int(_price)
            actual_price = int(_price)
            basic_price = int(_price)

            print('Price', _price)
    
    if not name:
        name = ' '.join(json_data.get('seo').get('title').split()[:4])

        print('NAMEEE FROM SEO', name)

    _sale = generate_sale_for_price(start_price)

    _data = {
        'link': link,
        'short_link': _new_short_link,
        'name': name,
        'actual_price': actual_price,
        'start_price': start_price,
        'basic_price': basic_price,
        'sale': _sale,
        'user_id': user_id,
        'photo_id': photo_id,
    }

    await add_product_to_db(_data,
                            'ozon',
                            is_first_product,
                            session)
    

async def try_update_wb_product_photo(product_id: int,
                                      short_link: str,
                                      session: AsyncSession):
    api_check_id_channel = -1002558196527

    # _url = f"{WB_API_URL}/product/image/{short_link}"
    _url = f"http://5.61.53.235:1435/product/image/{short_link}"
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession() as aiosession:
        async with aiosession.get(url=_url,
                                    timeout=timeout) as response:
            _status_code = response.status

            res = await response.text()
    try:
        image_data = base64.b64decode(res)

        image_name = 'test_image.png'

        async with aiofiles.open(image_name, 'wb') as file:
            await file.write(image_data)

        photo_msg = await bot.send_photo(chat_id=api_check_id_channel,
                                        photo=types.FSInputFile(path=f'./{image_name}'))
        
        if photo_msg.photo:
            photo_id = photo_msg.photo[0].file_id
    except Exception as ex:
        print(ex)
        # photo_id = TEST_PHOTO_ID
        photo_id = DEFAULT_PRODUCT_PHOTO_ID
    
    update_query = (
        update(
            Product
        )\
        .values(photo_id=photo_id)\
        .where(Product.id == product_id)
    )

    await session.execute(update_query)

    



async def try_get_wb_product_photo(short_link: str,
                                   session: AsyncSession):
    check_query = (
        select(
            Product.photo_id,
        )\
        .where(
            Product.short_link == short_link,
        )
    )

    async with session as _session:
        res = await _session.execute(check_query)

    product_photo = res.scalar_one_or_none()

    if product_photo:
        return product_photo

    api_check_id_channel = -1002558196527

    _url = f"http://5.61.53.235:1435/product/image/{short_link}"
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession() as aiosession:
        async with aiosession.get(url=_url,
                                    timeout=timeout) as response:
            _status_code = response.status

            res = await response.text()
    
    image_data = base64.b64decode(res)

    image_name = 'test_image.png'

    async with aiofiles.open(image_name, 'wb') as file:
        await file.write(image_data)

    photo_msg = await bot.send_photo(chat_id=api_check_id_channel,
                                     photo=types.FSInputFile(path=f'./{image_name}'))
    
    if photo_msg.photo:
        photo_id = photo_msg.photo[0].file_id

        return photo_id


async def save_wb_product(user_id: int,
                          link: str,
                          name: str | None,
                          is_first_product: bool,
                          session: AsyncSession):
    _prefix = 'catalog/'

    _idx_prefix = link.find(_prefix)

    short_link = link[_idx_prefix + len(_prefix):].split('/')[0]

    query = (
        select(
            UserProduct.id,
        )\
        .where(
            UserProduct.user_id == user_id,
            UserProduct.link == link,
        )
    )
    async with session as _session:
        res = await _session.execute(query)

    res = res.scalar_one_or_none()

    if res:
        raise WbProductExistsError()

    query = (
        select(
            Punkt.wb_zone,
            )\
        .join(User,
              Punkt.user_id == User.tg_id)\
        .where(User.tg_id == user_id)
    )
    async with session as _session:
        res = await _session.execute(query)

    del_zone = res.scalar_one_or_none()

    if not del_zone:
        del_zone = -1281648

    check_product_by_user =  await new_check_product_by_user_in_db(user_id=user_id,
                                                                   short_link=short_link,
                                                                   session=session)

    if check_product_by_user:
        raise WbProductExistsError()

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession() as aiosession:
        # _url = f"http://172.18.0.7:8080/product/{del_zone}/{short_link}"
        _url = f"http://5.61.53.235:1435/product/{del_zone}/{short_link}"
        async with aiosession.get(url=_url,
                        timeout=timeout) as response:

                res = await response.json()

    photo_id = await try_get_wb_product_photo(short_link=short_link,
                                              session=session)

    if not photo_id:
        print('Не удалось спарсить фото WB товара')
        raise Exception()

    d = res.get('data')

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

            _product_price = float(_product_price)

    print('WB price', _product_price)

    _sale = generate_sale_for_price(float(_product_price))

    _data_name = name if name else _product_name

    _data = {
        'link': link,
        'short_link': short_link,
        'start_price': _product_price,
        'actual_price': _product_price,
        'sale': _sale,
        'name': _data_name,
        'user_id': user_id,
        'photo_id': photo_id,
    }

    await add_product_to_db(_data,
                            'wb',
                            is_first_product,
                            session)


async def new_save_product(user_data: dict,
                           session: AsyncSession,
                           scheduler: AsyncIOScheduler):
    msg = user_data.get('msg')
    _name = user_data.get('name')
    link: str = user_data.get('link')
    link = link.split('?')[0]

    print('NAMEEE', _name)

    query = (
        select(
            UserProduct.id
        )\
        .where(
            UserProduct.user_id == msg[0]
        )
    )

    async with session as _session:
        res = await _session.execute(query)

    products_by_user = res.scalars().all()

    product_count_by_user = len(products_by_user)

    is_first_product = not bool(product_count_by_user)

    print(f'PRODUCT COUNT BY USER {msg[0]} {product_count_by_user}')

    if link.find('ozon') > 0:
        # save ozon product
        await save_ozon_product(user_id=msg[0],
                                link=link,
                                name=_name,
                                is_first_product=is_first_product,
                                session=session)

    elif link.find('wildberries') > 0:
        # save wb product
        await save_wb_product(user_id=msg[0],
                              link=link,
                              name=_name,
                              is_first_product=is_first_product,
                              session=session)


async def test_add_photo_to_exist_products():
    product_query = (
        select(
            Product.id,
            Product.product_marker,
            Product.short_link,
            Product.photo_id,
        )\
        .where(
            Product.photo_id.is_(None),
        )
    )

    async for session in get_session():
        async with session as _session:
            res = await _session.execute(product_query)
    
            for product in res:
                _id, marker, short_link, photo_id = product
                print('PRODUCT', product)

                if marker == 'wb':
                    if not photo_id:
                        await try_update_wb_product_photo(product_id=_id,
                                                            short_link=short_link,
                                                            session=_session)
                elif marker == 'ozon':
                    if not photo_id:
                        await try_update_ozon_product_photo(product_id=_id,
                                                            short_link=short_link,
                                                            session=_session)
                await asyncio.sleep(1.5)
            
            try:
                await _session.commit()
            except Exception as ex:
                print(ex)
                await _session.rollback()


async def test_migrate_on_new_sctucture_db():
    wb_query = (
        select(
            WbProduct,
            User,
        )\
        .join(User,
              WbProduct.user_id == User.tg_id)
    )
    async for session in get_session():
        async with session as _session:
            res = await _session.execute(wb_query)

        wb_products = res.fetchall()

        for wb_product, user in wb_products:
            wb_product: WbProduct
            user: User
            print(wb_product.name, f'{user.tg_id} {user.username}', sep='|')

            product_data = {
                'product_marker': 'wb',
                'short_link': wb_product.short_link,
                'name': wb_product.name,

            }
            if user.tg_id in (int(SUB_DEV_ID),):
                product = Product(**product_data)

                async with session as _session:
                    _session.add(product)

                    try:
                        await _session.flush()
                        await _session.commit()
                        product_id = product.id
                    except IntegrityError as ex:
                        print('catch exc!!!!')
                        print(ex)
                        await _session.rollback()

                        # async with session as _session:
                        query = (
                            select(
                                Product.id
                            )\
                            .where(
                                Product.short_link == wb_product.short_link
                            )
                        )
                        res = await _session.execute(query)

                        product_id = res.scalar_one_or_none()
                    # else:
                    print('ID PRODUCT', product_id)

                    wb_data = {
                        'product_id': product_id,
                        'link': wb_product.link,
                        'start_price': wb_product.start_price,
                        'actual_price': wb_product.actual_price,
                        'sale': wb_product.sale,
                        'time_create': wb_product.time_create,
                        'user_id': wb_product.user_id,
                    }

                    new_wb_product = UserProduct(**wb_data)

                    session.add(new_wb_product)
                    await session.flush()

                    new_wb_product_id = new_wb_product.id

                    #          user_id | marker | product_id
                    job_id = f'{user.tg_id}:wb:{new_wb_product_id}'
                    # job_id = 'test_job_id'

                    # if marker == 'wb':
                    scheduler_func = new_push_check_wb_price
                    # else:
                    #     scheduler_func = new_push_check_ozon_price

                    job = scheduler.add_job(scheduler_func,
                                            trigger='interval',
                                            minutes=15,
                                            id=job_id,
                                            jobstore='sqlalchemy',
                                            coalesce=True,
                                            kwargs={'user_id': user.tg_id,
                                                    'product_id': new_wb_product_id})
                    
                    _data = {
                        'user_product_id': new_wb_product_id,
                        'job_id': job.id,
                        # 'job_id': job_id,
                    }

                    user_job = UserProductJob(**_data)

                    session.add(user_job)

                    async with session as _session:
                        try:
                            await _session.commit()
                        except Exception as ex:
                            print(ex)
                            await _session.rollback()
            else:
                continue

    ozon_query = (
        select(
            OzonProduct,
            User,
        )\
        .join(User,
              OzonProduct.user_id == User.tg_id)
    )

    async for session in get_session():
        async with session as _session:
            res = await _session.execute(ozon_query)

        ozon_products = res.fetchall()

        for ozon_product, user in ozon_products:
            ozon_product: OzonProduct
            user: User
            print(ozon_product.name, f'{user.tg_id} {user.username}', sep='|')

            product_data = {
                'product_marker': 'ozon',
                'short_link': ozon_product.short_link,
                'name': ozon_product.name,

            }

            if user.tg_id in (int(SUB_DEV_ID),):
                product = Product(**product_data)

                # async for session in get_session():
                async with session as _session:
                    _session.add(product)

                    try:
                        await _session.flush()
                        await _session.commit()
                        product_id = product.id
                    except IntegrityError as ex:
                        print('catch exc!!!!')
                        print(ex)
                        await _session.rollback()

                        # async with session as _session:
                        query = (
                            select(
                                Product.id
                            )\
                            .where(
                                Product.short_link == ozon_product.short_link
                            )
                        )
                        res = await _session.execute(query)

                        product_id = res.scalar_one_or_none()
                # else:
                print('ID PRODUCT', product_id)

                ozon_data = {
                    'product_id': product_id,
                    'link': ozon_product.link,
                    'start_price': ozon_product.start_price,
                    'actual_price': ozon_product.actual_price,
                    'sale': ozon_product.sale,
                    'time_create': ozon_product.time_create,
                    'user_id': ozon_product.user_id,
                }

                new_ozon_product = UserProduct(**ozon_data)

                _session.add(new_ozon_product)

                await session.flush()

                new_ozon_product_id = new_ozon_product.id

                #          user_id | marker | product_id
                job_id = f'{user.tg_id}:ozon:{new_ozon_product_id}'
                # job_id = 'test_job_id'

                # if marker == 'wb':
                scheduler_func = new_push_check_ozon_price
                # else:
                #     scheduler_func = new_push_check_ozon_price

                job = scheduler.add_job(scheduler_func,
                                        trigger='interval',
                                        minutes=15,
                                        id=job_id,
                                        jobstore='sqlalchemy',
                                        coalesce=True,
                                        kwargs={'user_id': user.tg_id,
                                                'product_id': new_ozon_product_id})
                
                _data = {
                    'user_product_id': new_ozon_product_id,
                    'job_id': job.id,
                    # 'job_id': job_id,
                }

                user_job = UserProductJob(**_data)

                session.add(user_job)

                try:
                    await _session.commit()
                except Exception as ex:
                    print(ex)
                    await _session.rollback()
            else:
                continue

    print('DONE')


def startup_update_scheduler_jobs(scheduler: AsyncIOScheduler):
    jobs: list[Job] = scheduler.get_jobs(jobstore='sqlalchemy')

    print('start up update scheduler jobs...')
    for job in jobs:
        if job.id.find('wb') != -1 or job.id.find('ozon') != -1:
            if job.id.find('wb') != -1:
                if job.id.find(DEV_ID) != -1 or job.id.find(SUB_DEV_ID) != -1:
                    modify_func = new_push_check_wb_price
                else:
                    modify_func = push_check_wb_price
            else:
                if job.id.find(DEV_ID) != -1 or job.id.find(SUB_DEV_ID) != -1:
                    modify_func = new_push_check_ozon_price
                else:
                    modify_func = push_check_ozon_price
            
            job.modify(func=modify_func)
        
        elif job.id.find('delete_msg_task') != -1:
            modify_func = test_periodic_delete_old_message

            job.modify(func=modify_func,
                       trigger=scheduler_interval)


async def add_product_task(user_data: dict):
        try:
            product_marker: str = user_data.get('product_marker')
            _add_msg_id: int = user_data.get('_add_msg_id')
            msg: tuple = user_data.get('msg')

            async for session in get_session():
                check_product_limit = await check_subscription_limit(user_id=msg[0],
                                                                     marker=product_marker,
                                                                     session=session)
            if check_product_limit:
                _text = f'⛔ Достигнут лимит {product_marker.upper()} товаров по Вашей подписке ⛔\n\nЛимит товаров: {check_product_limit}'
                msg = await bot.edit_message_text(chat_id=msg[0],
                                                  message_id=_add_msg_id,
                                                  text=_text)
                await add_message_to_delete_dict(msg)
                return

            async for session in get_session():
                find_in_db = await save_product(user_data=user_data,
                                                session=session,
                                                scheduler=scheduler)
            
            if find_in_db:
                _text = f'{product_marker} товар уже был в Вашем списке или ошибка'
            else:
                _text = f'{product_marker} товар добавлен к отслеживанию✅'

            await bot.edit_message_text(chat_id=msg[0],
                                        message_id=_add_msg_id,
                                        text=_text)
                
        except Exception as ex:
            print('SCHEDULER ADD ERROR', ex)
            await bot.edit_message_text(chat_id=msg[0],
                                        message_id=_add_msg_id,
                                        text=f'{product_marker.upper()} не удалось добавить')


async def new_add_product_task(user_data: dict):
        try:
            product_marker: str = user_data.get('product_marker')
            _add_msg_id: int = user_data.get('_add_msg_id')
            msg: tuple = user_data.get('msg')

            async for session in get_session():
                check_product_limit = await new_check_subscription_limit(user_id=msg[0],
                                                                     marker=product_marker,
                                                                     session=session)
            if check_product_limit:
                _text = f'⛔ Достигнут лимит {product_marker.upper()} товаров по Вашей подписке ⛔\n\nЛимит товаров: {check_product_limit}'
                msg = await bot.edit_message_text(chat_id=msg[0],
                                                  message_id=_add_msg_id,
                                                  text=_text)
                await add_message_to_delete_dict(msg)
                return
            try:
                async for session in get_session():
                    await new_save_product(user_data=user_data,
                                           session=session,
                                           scheduler=scheduler)
            except (OzonProductExistsError, WbProductExistsError) as ex:
                print('PRODUCT EXISTS', ex)
                _text = f'❗️ {product_marker} товар уже есть в Вашем списке'
            except OzonAPICrashError as ex:
                print('OZON API CRASH', ex)
                pass
            except aiohttp.ClientError as ex:
                print('Таймаут по запросу к OZON API', ex)
            except Exception as ex:
                print(ex)
                _text = f'‼️ Возникла ошибка при добавлении {product_marker} товара\n\nПопробуйте повторить позже'
            else:
                _text = f'{product_marker} товар добавлен к отслеживанию✅'

            await bot.edit_message_text(chat_id=msg[0],
                                        message_id=_add_msg_id,
                                        text=_text)
                
        except Exception as ex:
            print('SCHEDULER ADD ERROR', ex)
            await bot.edit_message_text(chat_id=msg[0],
                                        message_id=_add_msg_id,
                                        text=f'{product_marker.upper()} не удалось добавить')


async def add_punkt_by_user(punkt_data: dict):
    punkt_action: str = punkt_data.get('punkt_action')
    # punkt_marker: str = punkt_data.get('punkt_marker')
    city: str = punkt_data.get('city')
    city_index: str = punkt_data.get('index')
    settings_msg: tuple = punkt_data.get('settings_msg')
    user_id: int = punkt_data.get('user_id')

    print(punkt_data)

    wb_punkt_model = WbPunkt
    ozon_punkt_model = OzonPunkt

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession() as aiosession:
            # if punkt_marker == 'wb':
            wb_url = f"{WB_API_URL}/pickUpPoint/{city_index}"
            # else:
            ozon_url = f"{OZON_API_URL}/pickUpPoint/{city_index}"

            # Wb
            async with aiosession.get(url=wb_url,
                            timeout=timeout) as response:
                wb_del_zone = await response.text()

                print('WB DEL ZONE', wb_del_zone)
            # Ozon
            async with aiosession.get(url=ozon_url,
                            timeout=timeout) as response:
                ozon_del_zone = await response.text()

                print('OZON DEL ZONE', ozon_del_zone)

    except Exception as ex:
        print('DEL ZONE REQUEST ERRROR', ex)
        await bot.edit_message_text(text='Что то пошло не так, просим прощения\n\nПопробуйте повторить позже',
                                    chat_id=settings_msg[0],
                                    message_id=settings_msg[-1])
        return
    
    try:
        wb_del_zone = int(wb_del_zone)
        ozon_del_zone = int(ozon_del_zone)
    except Exception as ex:
        print('RESPONSE ERROR WITH CONVERT DEL ZONE', ex)
        await bot.edit_message_text(text='Что то пошло не так, просим прощения\n\nПопробуйте повторить позже',
                                    chat_id=settings_msg[0],
                                    message_id=settings_msg[-1])
        return
    
    if punkt_action == 'add':
        wb_insert_data = {
            'user_id': user_id,
            'index': int(city_index),
            'city': city,
            'zone': wb_del_zone,
            'time_create': datetime.now(),
        }
        ozon_insert_data = {
            'user_id': user_id,
            'index': int(city_index),
            'city': city,
            'zone': ozon_del_zone,
            'time_create': datetime.now(),
        }

        wb_query = (
            insert(
                wb_punkt_model
            )\
            .values(**wb_insert_data)
        )
        ozon_query = (
            insert(
                ozon_punkt_model
            )\
            .values(**ozon_insert_data)
        )

        success_text = f'✅ Пункт выдачи успешно добавлен (Установленный город - {city}).'
        error_text = f'❌ Не получилось добавить пункт выдачи (Переданный город - {city})'

    elif punkt_action == 'edit':
        wb_update_data = {
            'city': city,
            'index': int(city_index),
            'zone': wb_del_zone,
            'time_create': datetime.now(),
        }
        ozon_update_data = {
            'city': city,
            'index': int(city_index),
            'zone': ozon_del_zone,
            'time_create': datetime.now(),
        }
        wb_query = (
            update(
                wb_punkt_model
            )\
            .values(**wb_update_data)\
            .where(wb_punkt_model.user_id == user_id)
        )
        ozon_query = (
            update(
                ozon_punkt_model
            )\
            .values(**ozon_update_data)\
            .where(ozon_punkt_model.user_id == user_id)
        )
        
        success_text = f'✅ Пункт выдачи успешно изменён (Новый установленный город - {city}).'
        error_text = f'❌ Не получилось изменить пункт выдачи (Переданный город - {city})'

    else:
        print('!!!!!!!!Такого не должно быть!!!!!!!!')
        return
    
    async for session in get_session():
        try:
            await session.execute(wb_query)
            await session.execute(ozon_query)
            await session.commit()
        except Exception as ex:
            await session.rollback()
            print('ADD/EDIT PUNKT BY USER ERRROR', ex)
            await bot.edit_message_text(text=error_text,
                                        chat_id=settings_msg[0],
                                        message_id=settings_msg[-1])
        else:
            await bot.edit_message_text(text=success_text,
                                        chat_id=settings_msg[0],
                                        message_id=settings_msg[-1])

    pass


async def new_add_punkt_by_user(punkt_data: dict):
    punkt_action: str = punkt_data.get('punkt_action')
    city: str = punkt_data.get('city')
    city_index: str = punkt_data.get('index')
    settings_msg: tuple = punkt_data.get('settings_msg')
    user_id: int = punkt_data.get('user_id')

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession() as aiosession:
            wb_url = f"{WB_API_URL}/pickUpPoint/{city_index}"
            ozon_url = f"{OZON_API_URL}/pickUpPoint/{city_index}"
            # wb_url = f"http://5.61.53.235:1435/pickUpPoint/{city_index}"
            # ozon_url = f"http://5.61.53.235:1441/pickUpPoint/{city_index}"

            # Wb
            async with aiosession.get(url=wb_url,
                                      timeout=timeout) as response:
                wb_del_zone = await response.text()

                print('WB DEL ZONE', wb_del_zone)
            # Ozon
            async with aiosession.get(url=ozon_url,
                                      timeout=timeout) as response:
                ozon_del_zone = await response.text()

                print('OZON DEL ZONE', ozon_del_zone)

    except Exception as ex:
        print('DEL ZONE REQUEST ERRROR', ex)
        await bot.edit_message_text(text='Что то пошло не так, просим прощения\n\nПопробуйте повторить позже',
                                    chat_id=settings_msg[0],
                                    message_id=settings_msg[-1])
        return
    
    try:
        wb_del_zone = int(wb_del_zone)
        ozon_del_zone = int(ozon_del_zone)
    except Exception as ex:
        print('RESPONSE ERROR WITH CONVERT DEL ZONE', ex)
        await bot.edit_message_text(text='Что то пошло не так, просим прощения\n\nПопробуйте повторить позже',
                                    chat_id=settings_msg[0],
                                    message_id=settings_msg[-1])
        return
    
    if punkt_action == 'add':
        insert_data = {
            'user_id': user_id,
            'index': int(city_index),
            'city': city,
            'ozon_zone': ozon_del_zone,
            'wb_zone': wb_del_zone,
            'time_create': datetime.now(),
        }

        query = (
            insert(
                Punkt
            )\
            .values(**insert_data)
        )
        success_text = f'✅ Пункт выдачи успешно добавлен (Установленный город - {city}).'
        error_text = f'❌ Не получилось добавить пункт выдачи (Переданный город - {city})'

    elif punkt_action == 'edit':
        update_data = {
            'city': city,
            'index': int(city_index),
            'ozon_zone': ozon_del_zone,
            'wb_zone': wb_del_zone,
            'time_create': datetime.now(),
        }
        query = (
            update(
                Punkt
            )\
            .values(**update_data)\
            .where(Punkt.user_id == user_id)
        )
        
        success_text = f'✅ Пункт выдачи успешно изменён (Новый установленный город - {city}).'
        error_text = f'❌ Не получилось изменить пункт выдачи (Переданный город - {city})'

    else:
        print('!!!!!!!!Такого не должно быть!!!!!!!!')
        return
    
    async for session in get_session():
        try:
            await session.execute(query)
            await session.commit()
        except Exception as ex:
            await session.rollback()
            print('ADD/EDIT PUNKT BY USER ERRROR', ex)
            await bot.edit_message_text(text=error_text,
                                        chat_id=settings_msg[0],
                                        message_id=settings_msg[-1])
        else:
            await bot.edit_message_text(text=success_text,
                                        chat_id=settings_msg[0],
                                        message_id=settings_msg[-1])


async def push_check_wb_price(user_id: str,
                              product_id: str):
    
    print(f'фоновая задача {user_id}')

    async for session in get_session():
        try:
            subquery = (
                select(UserJob.job_id,
                    UserJob.user_id,
                    UserJob.product_id)
                .where(UserJob.user_id == user_id)
            ).subquery()

            query = (
                select(
                    User.username,
                    WbProduct.link,
                    WbProduct.short_link,
                    WbProduct.actual_price,
                    WbProduct.start_price,
                    WbProduct.name,
                    WbProduct.sale,
                    WbPunkt.zone,
                    subquery.c.job_id,
                )\
                .select_from(WbProduct)\
                .outerjoin(WbPunkt,
                            WbProduct.wb_punkt_id == WbPunkt.id)\
                .join(User,
                        WbProduct.user_id == User.tg_id)\
                .outerjoin(subquery,
                            subquery.c.product_id == WbProduct.id)\
                .where(
                    and_(
                        User.tg_id == user_id,
                        WbProduct.id == product_id,
                    ))\
                .distinct(WbProduct.id)
            )

            res = await session.execute(query)

            res = res.fetchall()
        finally:
            try:
                await session.close()
            except Exception:
                pass
    if res:
        username, link, short_link, actual_price, start_price, _name, sale, zone, job_id = res[0]

        if not zone:
            zone = -1281648

        name = _name if _name is not None else 'Отсутствует'
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession() as aiosession:
                _url = f"http://172.18.0.7:8080/product/{zone}/{short_link}"
                
                async with aiosession.get(url=_url,
                            timeout=timeout) as response:
                    res = await response.json()

            d = res.get('data')


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

            _product_price = float(_product_price)

            print(f'TEST PRICE PROBLEM {_product_price} | {actual_price}')
            
            check_price = _product_price == actual_price

            if check_price:
                _text = 'цена не изменилась'
                print(f'{_text} user {user_id} product {_name}')
                return
            else:

                query = (
                    update(
                        WbProduct
                    )\
                    .values(actual_price=_product_price)\
                    .where(WbProduct.id == product_id)
                )
                async for session in get_session():
                    try:
                        await session.execute(query)
                        await session.commit()
                    except Exception as ex:
                        await session.rollback()
                        print(ex)

                _waiting_price = start_price - sale

                pretty_product_price = generate_pretty_amount(_product_price)
                pretty_actual_price = generate_pretty_amount(actual_price)
                pretty_sale = generate_pretty_amount(sale)
                pretty_waiting_price = generate_pretty_amount(_waiting_price)
                pretty_start_price = generate_pretty_amount(start_price)
                
                if _waiting_price >= _product_price:

                    if actual_price < _product_price:
                        _text = f'🔄 Цена повысилась, но всё ещё входит в выставленный диапазон скидки на товар <a href="{link}">{_name}</a>\n\nМаркетплейс: Wb\n🔄Отслеживаемая скидка: {pretty_sale}\n\n⬇️Цена по карте: {pretty_product_price} (дешевле на {start_price - _product_price}₽)\n\nНачальная цена: {pretty_start_price}\n\nПредыдущая цена: {pretty_actual_price}'
                        _disable_notification = True
                    else:
                        _text = f'🚨 Изменилась цена на <a href="{link}">{_name}</a>\n\nМаркетплейс: Wb\n🔄Отслеживаемая скидка: {pretty_sale}\n\n⬇️Цена по карте: {pretty_product_price} (дешевле на {start_price - _product_price}₽)\n\nНачальная цена: {pretty_start_price}\n\nПредыдущая цена: {pretty_actual_price}'
                        _disable_notification = False

                    _kb = create_remove_and_edit_sale_kb(user_id=user_id,
                                                        product_id=product_id,
                                                        marker='wb',
                                                        job_id=job_id,
                                                        with_redirect=False)

                    _kb = add_or_create_close_kb(_kb)

                    msg = await bot.send_message(chat_id=user_id,
                                                 text=_text,
                                                 disable_notification=_disable_notification,
                                                 reply_markup=_kb.as_markup())
                    await add_message_to_delete_dict(msg)
                    return

        except Exception as ex:
            print(ex)
            pass
                

async def push_check_ozon_price(user_id: str,
                              product_id: str):
    
    print(f'фоновая задача {user_id}')

    async for session in get_session():
        async with session as _session:
            try:
                subquery = (
                    select(UserJob.job_id,
                        UserJob.user_id,
                        UserJob.product_id)
                    .where(UserJob.user_id == user_id)
                ).subquery()

                query = (
                    select(
                        User.username,
                        OzonProduct.link,
                        OzonProduct.short_link,
                        OzonProduct.actual_price,
                        OzonProduct.start_price,
                        OzonProduct.name,
                        OzonProduct.sale,
                        OzonPunkt.zone,
                        subquery.c.job_id,
                    )\
                    .select_from(OzonProduct)\
                    .join(User,
                          OzonProduct.user_id == User.tg_id)\
                    .outerjoin(OzonPunkt,
                                OzonProduct.ozon_punkt_id == OzonPunkt.id)\
                    .outerjoin(subquery,
                               subquery.c.product_id == OzonProduct.id)\
                    .where(
                        and_(
                            User.tg_id == user_id,
                            OzonProduct.id == product_id,
                        ))\
                    .distinct(OzonProduct.id)
                )

                res = await _session.execute(query)

                res = res.fetchall()
            finally:
                try:
                    await _session.close()
                except Exception:
                    pass
    if res:
        username, link, short_link, actual_price, start_price, _name, sale, zone, job_id = res[0]

        _name = _name if _name is not None else 'Отсутствует'
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession() as aiosession:
                if zone:
                    _url = f"http://172.18.0.6:8080/product/{zone}/{short_link}"    
                # _url = f"http://5.61.53.235:1441/product/{message.text}"
                else:
                    _url = f"http://172.18.0.6:8080/product/{short_link}"
                async with aiosession.get(url=_url,
                            timeout=timeout) as response:

                    print(response.status)

                    if response.status == 408:
                        print('OZON TIMEOUT')
                        return

                    res = await response.text()

            w = re.findall(r'\"cardPrice.*currency?', res)

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

                _product_price = _d.get('cardPrice', 0)
            else:
                try:
                    response_data = res.split('|')[-1]

                    json_data: dict = json.loads(response_data)

                    script_list = json_data.get('seo').get('script')

                    inner_html = script_list[0].get('innerHTML') #.get('offers').get('price')

                    inner_html_json: dict = json.loads(inner_html)
                    offers = inner_html_json.get('offers')

                    _price = offers.get('price')

                    _product_price = _price
                    
                    print('Price', _price)
                except Exception as ex:
                    print('scheduler parse inner html error', ex)
                    return

#
            _product_price = float(_product_price)

            print(f'TEST PRICE PROBLEM {_product_price} | {actual_price}')
            
            check_price = _product_price == actual_price

            if check_price:
                _text = 'цена не изменилась'
                print(f'{_text} user {user_id} product {_name}')
                return
            else:
                _waiting_price = start_price - sale

                query = (
                    update(
                        OzonProduct
                    )\
                    .values(actual_price=_product_price)\
                    .where(OzonProduct.id == product_id)
                )
                async for session in get_session():
                    async with session as _session:
                        try:
                            await session.execute(query)
                            await session.commit()
                        except Exception as ex:
                            await session.rollback()
                            print(ex)

                pretty_product_price = generate_pretty_amount(_product_price)
                pretty_actual_price = generate_pretty_amount(actual_price)
                pretty_sale = generate_pretty_amount(sale)
                pretty_waiting_price = generate_pretty_amount(_waiting_price)
                pretty_start_price = generate_pretty_amount(start_price)

                if _waiting_price >= _product_price:

                    if actual_price < _product_price:
                        _text = f'🔄 Цена повысилась, но всё ещё входит в выставленный диапазон скидки на товар <a href="{link}">{_name}</a>\n\nМаркетплейс: Ozon\n🔄Отслеживаемая скидка: {pretty_sale}\n\n⬇️Цена по карте: {pretty_product_price} (дешевле на {start_price - _product_price}₽)\n\nНачальная цена: {pretty_start_price}\n\nПредыдущая цена: {pretty_actual_price}'
                        _disable_notification = True
                    else:
                        _text = f'🚨 Изменилась цена на <a href="{link}">{_name}</a>\n\nМаркетплейс: Ozon\n🔄Отслеживаемая скидка: {pretty_sale}\n\n⬇️Цена по карте: {pretty_product_price} (дешевле на {start_price - _product_price}₽)\n\nНачальная цена: {pretty_start_price}\n\nПредыдущая цена: {pretty_actual_price}'
                        _disable_notification = False

                    _kb = create_remove_and_edit_sale_kb(user_id=user_id,
                                                        product_id=product_id,
                                                        marker='ozon',
                                                        job_id=job_id,
                                                        with_redirect=False)

                    _kb = add_or_create_close_kb(_kb)

                    msg = await bot.send_message(chat_id=user_id,
                                                 text=_text,
                                                 disable_notification=_disable_notification,
                                                 reply_markup=_kb.as_markup())
                    await add_message_to_delete_dict(msg)
                    return

        except Exception as ex:
            print('OZON SCHEDULER ERROR', ex)


async def try_add_product_price_to_db(product_id: int,
                                      city: str | None,
                                      price: float):

    city = city if city else 'МОСКВА'

    check_monitoring_price_query = (
        select(
            ProductPrice.time_price,
        )\
        .where(
            and_(
                ProductPrice.product_id == product_id,
                ProductPrice.city == city,
            )
        )\
        .order_by(
            desc(ProductPrice.time_price)
            )
    )

    async for session in get_session():
        async with session as _session:
            res = await _session.execute(check_monitoring_price_query)
    
    first_element_date = res.scalars().first()

    if first_element_date:
        print('first_element_date', first_element_date)
        check_date = datetime.now().astimezone(tz=timezone) - timedelta(hours=12)

        if first_element_date > check_date:
            print('early yet')
            return

    monitoring_price_data = {
        'product_id': product_id,
        'city': city,
        'price': price,
        'time_price': datetime.now(),
    }

    monitoring_price_query = (
        insert(
            ProductPrice
        )\
        .values(**monitoring_price_data)
    )

    async for session in get_session():
        async with session as _session:
            try:
                await session.execute(monitoring_price_query)
                await session.commit()
            except Exception as ex:
                await session.rollback()
                print(ex)


async def new_push_check_ozon_price(user_id: str,
                                    product_id: str):
    
    print(f'new фоновая задача ozon {user_id}')

    async for session in get_session():
        async with session as _session:
            try:
                query = (
                    select(
                        Product.id,
                        UserProduct.id,
                        UserProduct.link,
                        Product.short_link,
                        UserProduct.actual_price,
                        UserProduct.start_price,
                        Product.name,
                        UserProduct.sale,
                        Punkt.ozon_zone,
                        Punkt.city,
                        UserProductJob.job_id,
                        Product.photo_id,
                    )\
                    .select_from(UserProduct)\
                    .join(Product,
                          UserProduct.product_id == Product.id)\
                    .outerjoin(Punkt,
                               Punkt.user_id == int(user_id))\
                    .outerjoin(UserProductJob,
                               UserProductJob.user_product_id == UserProduct.id)\
                    .where(
                        and_(
                            UserProduct.id == int(product_id),
                            UserProduct.user_id == int(user_id),
                        )
                    )
                )

                res = await _session.execute(query)

                res = res.fetchall()
            finally:
                try:
                    await _session.close()
                except Exception:
                    pass
    if res:
        main_product_id, _id, link, short_link, actual_price, start_price, name, sale, zone, city, job_id, photo_id = res[0]

        name = name if name is not None else 'Отсутствует'
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession() as aiosession:
                if zone:
                    # _url = f"{OZON_API_URL}/product/{zone}/{short_link}"
                    _url = f"http://5.61.53.235:1441/product/{zone}/{short_link}"
                else:
                    # _url = f"{OZON_API_URL}/product/{short_link}"
                    _url = f"http://5.61.53.235:1441/product/{short_link}"
                async with aiosession.get(url=_url,
                            timeout=timeout) as response:
                    _status_code = response.status

                    print(_status_code)

                    res = await response.text()
                
                if _status_code == 404:
                    raise OzonAPICrashError()

            w = re.findall(r'\"cardPrice.*currency?', res)

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
                                _name, price = q.split(':')
                                price = price.replace('\\', '').replace('"', '')
                                price = float(''.join(price.split()[:-1]))
                                # print(price)
                                _d[k] = price
                                break
                    else:
                        break

                print(_d)

                _product_price = _d.get('cardPrice', 0)
            else:
                try:
                    response_data = res.split('|')[-1]

                    json_data: dict = json.loads(response_data)

                    script_list = json_data.get('seo').get('script')

                    inner_html = script_list[0].get('innerHTML') #.get('offers').get('price')

                    inner_html_json: dict = json.loads(inner_html)
                    offers = inner_html_json.get('offers')

                    _price = offers.get('price')

                    _product_price = _price
                    
                    print('Price', _price)
                except Exception as ex:
                    print('scheduler parse inner html error', ex)
                    return

            _product_price = float(_product_price)

            await try_add_product_price_to_db(product_id=main_product_id,
                                              city=city,
                                              price=_product_price)

            check_price = _product_price == actual_price

            if check_price:
                _text = 'цена не изменилась'
                print(f'{_text} user {user_id} product {name}')
                return
            else:
                _waiting_price = start_price - sale

                update_query = (
                    update(
                        UserProduct
                    )\
                    .values(actual_price=_product_price)\
                    .where(UserProduct.id == product_id)
                )

                async for session in get_session():
                    async with session as _session:
                        try:
                            await session.execute(update_query)
                            await session.commit()
                        except Exception as ex:
                            await session.rollback()
                            print(ex)

                pretty_product_price = generate_pretty_amount(_product_price)
                pretty_actual_price = generate_pretty_amount(actual_price)
                pretty_sale = generate_pretty_amount(sale)
                pretty_start_price = generate_pretty_amount(start_price)

                if _waiting_price >= _product_price:

                    if actual_price < _product_price:
                        _text = f'🔄 Цена повысилась, но всё ещё входит в выставленный диапазон скидки на товар <a href="{link}">{name}</a>\n\nМаркетплейс: Ozon\n🔄Отслеживаемая скидка: {pretty_sale}\n\n⬇️Цена по карте: {pretty_product_price} (дешевле на {start_price - _product_price}₽)\n\nНачальная цена: {pretty_start_price}\n\nПредыдущая цена: {pretty_actual_price}'
                        _disable_notification = True
                    else:
                        _text = f'🚨 Изменилась цена на <a href="{link}">{name}</a>\n\nМаркетплейс: Ozon\n🔄Отслеживаемая скидка: {pretty_sale}\n\n⬇️Цена по карте: {pretty_product_price} (дешевле на {start_price - _product_price}₽)\n\nНачальная цена: {pretty_start_price}\n\nПредыдущая цена: {pretty_actual_price}'
                        _disable_notification = False

                    _kb = new_create_remove_and_edit_sale_kb(user_id=user_id,
                                                             product_id=product_id,
                                                             marker='ozon',
                                                             job_id=job_id,
                                                             with_redirect=False)
                    
                    # _kb = add_graphic_btn(_kb,
                    #                       user_id=user_id,
                    #                       product_id=_id)

                    _kb = add_or_create_close_kb(_kb)

                    # msg = await bot.send_message(chat_id=user_id,
                    #                              text=_text,
                    #                              disable_notification=_disable_notification,
                    #                              reply_markup=_kb.as_markup())
                    msg = await bot.send_photo(chat_id=user_id,
                                               photo=photo_id,
                                               caption=_text,
                                               disable_notification=_disable_notification,
                                               reply_markup=_kb.as_markup())

                    await add_message_to_delete_dict(msg)
                    return

        except OzonAPICrashError as ex:
            print('SCHEDULER OZON API CRUSH', ex)

        except Exception as ex:
            print('OZON SCHEDULER ERROR', ex, ex.args)


async def new_push_check_wb_price(user_id: str,
                                  product_id: str):
    print(f'new фоновая задача wb {user_id}')

    async for session in get_session():
        async with session as _session:
            try:
                query = (
                    select(
                        Product.id,
                        UserProduct.id,
                        UserProduct.link,
                        Product.short_link,
                        UserProduct.actual_price,
                        UserProduct.start_price,
                        Product.name,
                        UserProduct.sale,
                        Punkt.wb_zone,
                        Punkt.city,
                        UserProductJob.job_id,
                        Product.photo_id,
                    )\
                    .select_from(UserProduct)\
                    .join(Product,
                          UserProduct.product_id == Product.id)\
                    .outerjoin(Punkt,
                               Punkt.user_id == int(user_id))\
                    .outerjoin(UserProductJob,
                               UserProductJob.user_product_id == UserProduct.id)\
                    .where(
                        and_(
                            UserProduct.id == int(product_id),
                            UserProduct.user_id == int(user_id),
                        )
                    )
                )

                res = await _session.execute(query)

                res = res.fetchall()
            finally:
                try:
                    await _session.close()
                except Exception:
                    pass
    if res:
        main_product_id, _id, link, short_link, actual_price, start_price, name, sale, zone, city, job_id, photo_id = res[0]

        name = name if name is not None else 'Отсутствует'

        if not zone:
            zone = -1281648

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession() as aiosession:
                _url = f"{WB_API_URL}/product/{zone}/{short_link}"
                # _url = f"http://5.61.53.235:1435/product/{zone}/{short_link}"
                
                async with aiosession.get(url=_url,
                                          timeout=timeout) as response:
                    _status_code = response.status

                    res = await response.json()

            if _status_code == 404:
                raise WbAPICrashError()

            d = res.get('data')

            sizes = d.get('products')[0].get('sizes')

            _basic_price = _product_price = None
            
            for size in sizes:
                _price = size.get('price')
                
                if _price:
                    _basic_price = size.get('price').get('basic')
                    _product_price = size.get('price').get('product')

                    _basic_price = str(_basic_price)[:-2]
                    _product_price = str(_product_price)[:-2]

            _product_price = float(_product_price)

            print('Wb price', _product_price)

            await try_add_product_price_to_db(product_id=main_product_id,
                                              city=city,
                                              price=_product_price)
            
            check_price = _product_price == actual_price

            if check_price:
                _text = 'цена не изменилась'
                print(f'{_text} user {user_id} product {name}')
                return
            
            else:
                update_query = (
                    update(
                        UserProduct
                    )\
                    .values(actual_price=_product_price)\
                    .where(UserProduct.id == product_id)
                )

                async for session in get_session():
                    async with session as _session:
                        try:
                            await session.execute(update_query)
                            await session.commit()
                        except Exception as ex:
                            await session.rollback()
                            print(ex)

                _waiting_price = start_price - sale

                pretty_product_price = generate_pretty_amount(_product_price)
                pretty_actual_price = generate_pretty_amount(actual_price)
                pretty_sale = generate_pretty_amount(sale)
                pretty_start_price = generate_pretty_amount(start_price)
                
                if _waiting_price >= _product_price:

                    if actual_price < _product_price:
                        _text = f'🔄 Цена повысилась, но всё ещё входит в выставленный диапазон скидки на товар <a href="{link}">{name}</a>\n\nМаркетплейс: Wb\n🔄Отслеживаемая скидка: {pretty_sale}\n\n⬇️Цена по карте: {pretty_product_price} (дешевле на {start_price - _product_price}₽)\n\nНачальная цена: {pretty_start_price}\n\nПредыдущая цена: {pretty_actual_price}'
                        _disable_notification = True
                    else:
                        _text = f'🚨 Изменилась цена на <a href="{link}">{name}</a>\n\nМаркетплейс: Wb\n🔄Отслеживаемая скидка: {pretty_sale}\n\n⬇️Цена по карте: {pretty_product_price} (дешевле на {start_price - _product_price}₽)\n\nНачальная цена: {pretty_start_price}\n\nПредыдущая цена: {pretty_actual_price}'
                        _disable_notification = False

                    _kb = new_create_remove_and_edit_sale_kb(user_id=user_id,
                                                             product_id=product_id,
                                                             marker='wb',
                                                             job_id=job_id,
                                                             with_redirect=False)
                    # _kb = add_graphic_btn(_kb,
                    #                       user_id=user_id,
                    #                       product_id=_id)

                    _kb = add_or_create_close_kb(_kb)

                    # msg = await bot.send_message(chat_id=user_id,
                    #                              text=_text,
                    #                              disable_notification=_disable_notification,
                    #                              reply_markup=_kb.as_markup())
                    msg = await bot.send_photo(chat_id=user_id,
                                               photo=photo_id,
                                               caption=_text,
                                               disable_notification=_disable_notification,
                                               reply_markup=_kb.as_markup())

                    await add_message_to_delete_dict(msg)
                    return

        except WbAPICrashError as ex:
            print('SCHEDULER WB API CRUSH', ex)

        except Exception as ex:
            print(ex)
            pass
