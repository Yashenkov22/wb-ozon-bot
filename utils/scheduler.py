import json
import re
import pytz
import aiohttp
import asyncio

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

from sqlalchemy import insert, select, and_, update, func

from db.base import OzonPunkt, Subscription, WbProduct, WbPunkt, User, get_session, UserJob, OzonProduct

from keyboards import add_or_create_close_kb, create_remove_and_edit_sale_kb, create_remove_kb

from bot22 import bot

from .storage import redis_client
from .any import generate_pretty_amount, generate_sale_for_price, add_message_to_delete_dict
from .cities import city_index_dict

from config import DEV_ID


JOB_STORE_URL = "postgresql+psycopg2://postgres:22222@psql_db/postgres"


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
        async with session as session:
            res = await session.execute(query)

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
        async with session as session:
            res = await session.execute(query)

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

        async with session.begin():
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
                await session.commit()
            except Exception as ex:
                print(ex)
                _text = 'Что то пошло не так'
                return True
            else:
                _text = 'Wb товар успешно добавлен'
                print(_text)
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


def startup_update_scheduler_jobs(scheduler: AsyncIOScheduler):
    jobs: list[Job] = scheduler.get_jobs(jobstore='sqlalchemy')

    print('start up update scheduler jobs...')

    for job in jobs:
        if job.id.find('wb') != -1 or job.id.find('ozon') != -1:
            if job.id.find('wb') > 0:
                modify_func = push_check_wb_price
            else:
                modify_func = push_check_ozon_price
            
            job.modify(func=modify_func)
        
        elif job.id.find('delete_msg_task') != -1:
            # if job.id.find('686339126') != -1:
            modify_func = test_periodic_delete_old_message
            # else:
            #     modify_func = periodic_delete_old_message
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
            wb_url = f"http://172.18.0.7:8080/pickUpPoint/{city_index}"
            # else:
            ozon_url = f"http://172.18.0.6:8080/pickUpPoint/{city_index}"

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



async def test_scheduler(user_id: str):
    # user_id = message.from_user.id

    await bot.send_message(chat_id=user_id,
                           text='test scheduler every 30 sec')