import json
import re
import pytz
import aiohttp

from aiogram import types, Bot

from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.job import Job

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select, and_, update

from db.base import WbProduct, WbPunkt, User, get_session, UserJob, OzonProduct

from keyboards import add_or_create_close_kb, create_remove_kb

from bot22 import bot

from .any import generate_pretty_amount


timezone = pytz.timezone('Europe/Moscow')

scheduler_cron = CronTrigger(minute=1,
                             timezone=timezone)


def startup_update_scheduler_jobs(scheduler: AsyncIOScheduler):
    jobs: list[Job] = scheduler.get_jobs(jobstore='sqlalchemy')

    print('start up update scheduler jobs...')

    for job in jobs:
        if job.id.find('wb') > 0:
            modify_func = push_check_wb_price
        else:
            modify_func = push_check_ozon_price
        
        job.modify(func=modify_func)


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
                .join(WbPunkt,
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

        name = _name if _name is not None else 'Отсутствует'
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession() as aiosession:
                _url = f"http://172.18.0.2:8080/product/{zone}/{short_link}"
                async with aiosession.get(url=_url,
                            timeout=timeout) as response:
                # response = await aiosession.get(url=_url)
                    res = await response.json()

            d = res.get('data')

            # print(d.get('products')[0].get('sizes'))

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
            else:
                # _waiting_price = None
                # if percent:
                #     _waiting_price = start_price - ((start_price * percent) / 100)

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
                # if _waiting_price == actual_price:
                _waiting_price = start_price - sale

                pretty_product_price = generate_pretty_amount(_product_price)
                pretty_actual_price = generate_pretty_amount(actual_price)
                pretty_sale = generate_pretty_amount(sale)
                pretty_waiting_price = generate_pretty_amount(_waiting_price)

                _text = f'WB товар\n{_name[:21]}\n<a href="{link}">Ссылка на товар</a>\nУстановленная скидка: {pretty_sale}\nЦена изменилась\nОбновленная цена товара: {pretty_product_price} (было {pretty_actual_price})'

                if _waiting_price >= _product_price:
                    _text = f'WB товар\nНазвание: {name[:21]}\n<a href="{link}">Ссылка на товар</a>\nУстановленная скидка: {pretty_sale}\nЦена товара, которую(или ниже) Вы ждали ({pretty_waiting_price})\nОбновленная цена товара: {pretty_product_price} (было {pretty_actual_price})'
                    
                    _kb = create_remove_kb(user_id,
                                            product_id,
                                            marker='wb',
                                            job_id=job_id,
                                            with_redirect=False)
                    
                    _kb = add_or_create_close_kb(_kb)

                    await bot.send_message(chat_id=user_id,
                                            text=_text,
                                            reply_markup=_kb.as_markup())
                    return
                if _product_price < actual_price:
                    await bot.send_message(chat_id=user_id,
                                            text=_text)
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
                        subquery.c.job_id,
                    )\
                    .select_from(OzonProduct)\
                    .join(User,
                          OzonProduct.user_id == User.tg_id)\
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
        username, link, short_link, actual_price, start_price, _name, sale, job_id = res[0]

        _name = _name if _name is not None else 'Отсутствует'
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession() as aiosession:
                # _url = f"http://5.61.53.235:1441/product/{message.text}"
                _url = f"http://172.18.0.7:8080/product/{short_link}"
                async with aiosession.get(url=_url,
                            timeout=timeout) as response:

                # response = await aiosession.get(url=_url)

                    print(response.status)

                    if response.status == 408:
                        print('OZON TIMEOUT')
                        return

                    res = await response.text()

            print('RES FROM OZON API', res)
            __response_data = res.split('|')[-1]

            __json_data: dict = json.loads(__response_data)

            print(__json_data)

            w = re.findall(r'\"cardPrice.*currency?', res)
            # print(w)

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
                # start_price = _d.get('cardPrice', 0)
                _product_price = _d.get('cardPrice', 0)
                # basic_price = _d.get('price', 0)
            else:
                try:
                    response_data = res.split('|')[-1]

                    json_data: dict = json.loads(response_data)

                    script_list = json_data.get('seo').get('script')

                    # if v:
                    #     t = v.get('script')

                    # if script_list:
                    inner_html = script_list[0].get('innerHTML') #.get('offers').get('price')

                    print('innerHTML', inner_html)

                    # if inner_html:
                        # print(type(b))
                        # try:
                    inner_html_json: dict = json.loads(inner_html)
                    offers = inner_html_json.get('offers')

                    # print(offers)

                    _price = offers.get('price')

                    # start_price = _price
                    _product_price = _price
                    # basic_price = _price

                    # price_dict = {
                    #     'ozon_start_price': 0,
                    #     'ozon_actual_price': float(_p),
                    #     'ozon_basic_price': float(_p),
                    # }

                    # await state.update_data(data=price_dict)
                    
                    print('Price', _price)
                        # except Exception as ex:
                        #     print('problem', ex)
                            # return
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
                # if percent:
                #     _waiting_price = start_price - ((start_price * percent) / 100)

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
                    # if _waiting_price == actual_price:

                pretty_product_price = generate_pretty_amount(_product_price)
                pretty_actual_price = generate_pretty_amount(actual_price)
                pretty_sale = generate_pretty_amount(sale)
                pretty_waiting_price = generate_pretty_amount(_waiting_price)
                
                _text = f'Ozon товар\n{_name[:21]}\n<a href="{link}">Ссылка на товар</a>\n\nУстановленная скидка: {pretty_sale}\nЦена изменилась\nОбновленная цена товара: {pretty_product_price}\n(было {pretty_actual_price})'
                
                # if _waiting_price:
                if _waiting_price >= _product_price:
                    _text = f'Ozon товар\n{_name[:21]}\n<a href="{link}">Ссылка на товар</a>\n\nУстановленная скидка: {pretty_sale}\nЦена товара, которую(или ниже) Вы ждали\nОбновленная цена товара: {pretty_product_price}\n(было {pretty_actual_price})'
                    
                    _kb = create_remove_kb(user_id,
                                            product_id,
                                            marker='ozon',
                                            job_id=job_id,
                                            with_redirect=False)
                    
                    _kb = add_or_create_close_kb(_kb)

                    await bot.send_message(chat_id=user_id,
                                            text=_text,
                                            reply_markup=_kb.as_markup())
                    return
                    
                    # if _product_price < actual_price:
                    #     await bot.send_message(chat_id=user_id,
                    #                             text=_text,
                    #                             reply_markup=_kb.as_markup())
                    #     return

            # else:
                # try:
                #     response_data = res.split('|')[-1]

                #     json_data: dict = json.loads(response_data)

                #     script_list = json_data.get('seo').get('script')

                #     # if v:
                #     #     t = v.get('script')

                #     if script_list:
                #         inner_html = script_list[0].get('innerHTML') #.get('offers').get('price')

                #         print('innerHTML', inner_html)

                #         if inner_html:
                #             # print(type(b))
                #             try:
                #                 inner_html_json: dict = json.loads(inner_html)
                #                 offers = inner_html_json.get('offers')

                #                 # print(offers)

                #                 _price = offers.get('price')

                #                 start_price = _price
                #                 actual_price = _price
                #                 basic_price = _price

                #                 # price_dict = {
                #                 #     'ozon_start_price': 0,
                #                 #     'ozon_actual_price': float(_p),
                #                 #     'ozon_basic_price': float(_p),
                #                 # }

                #                 # await state.update_data(data=price_dict)
                                
                #                 print('Price', _price)
                #             except Exception as ex:
                                
                #                 print('problem', ex)



                        # print('\nV', v)
                        # print('\nT', t)
                #     else:
                #         print('problem')
                #         return
                # except Exception as ex:
                #     print(ex)
                # _text = f'Не получилось спарсить цену {_name}'
                # print(f'{_text} {res[:100]}')
                # return

            # await bot.send_message(chat_id=user_id,
            #                         text=_text)
        except Exception as ex:
            print('OZON SCHEDULER ERROR', ex)



async def test_scheduler(user_id: str):
    # user_id = message.from_user.id

    await bot.send_message(chat_id=user_id,
                           text='test scheduler every 30 sec')