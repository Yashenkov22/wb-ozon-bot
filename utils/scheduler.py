import re
import pytz
import aiohttp

from aiogram import types, Bot

from apscheduler.triggers.cron import CronTrigger

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select, and_, update

from db.base import WbProduct, WbPunkt, User, get_session, UserJob, OzonProduct

from keyboards import add_or_create_close_kb, create_remove_kb

from bot22 import bot


timezone = pytz.timezone('Europe/Moscow')

scheduler_cron = CronTrigger(minute=1,
                             timezone=timezone)


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
                    WbProduct.percent,
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
        username, link, short_link, actual_price, start_price, _name, percent, zone, job_id = res[0]

        name = _name if _name is not None else 'Отсутствует'

        async with aiohttp.ClientSession() as aiosession:
            _url = f"http://172.18.0.2:8080/product/{zone}/{short_link}"
            response = await aiosession.get(url=_url)
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
                _waiting_price = None
                if percent:
                    _waiting_price = start_price - ((start_price * percent) / 100)

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
                _text = f'WB товар\n{_name[:21]}\n<a href="{link}"Ссылка на товар</a>\nЦена изменилась\nОбновленная цена товара: {_product_price} (было {actual_price})'

                if _waiting_price and _waiting_price >= _product_price:
                    _text = f'WB товар\nНазвание: {name[:21]}\nЦена товара, которую(или ниже) Вы ждали\nОбновленная цена товара: {_product_price} (было {actual_price})'
                    
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
                
                await bot.send_message(chat_id=user_id,
                                        text=_text)
            

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
                        OzonProduct.percent,
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
        username, link, short_link, actual_price, start_price, _name, percent, job_id = res[0]

        _name = _name if _name is not None else 'Отсутствует'
        try:
            async with aiohttp.ClientSession() as aiosession:
                # _url = f"http://5.61.53.235:1441/product/{message.text}"
                _url = f"http://172.18.0.4:8080/product/{short_link}"

                response = await aiosession.get(url=_url)

                print(response.status)

                res = await response.text()

                # print(res)

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

                _product_price = float(_d.get('cardPrice'))
                
                check_price = _product_price == actual_price

                if check_price:
                    _text = 'цена не изменилась'
                    print(f'{_text} user {user_id} product {_name}')
                    return
                else:
                    _waiting_price = None
                    if percent:
                        _waiting_price = start_price - ((start_price * percent) / 100)

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
                    
                    _text = f'Ozon товар\n{_name[:21]}\n<a href="{link}"Ссылка на товар</a>\nЦена изменилась\nОбновленная цена товара: {_product_price} (было {actual_price})'
                    
                    if _waiting_price:
                        if _waiting_price >= _product_price:
                            _text = f'Ozon товар\n{_name[:21]}\nЦена товара, которую(или ниже) Вы ждали\nОбновленная цена товара: {_product_price} (было {actual_price})'
                            
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
            else:
                _text = f'Не получилось спарсить цену {_name}'
                print(f'{_text} {res[:100]}')

            await bot.send_message(chat_id=user_id,
                                    text=_text)
        except Exception as ex:
            print('OZON SCHEDULER ERROR', ex)



async def test_scheduler(user_id: str):
    # user_id = message.from_user.id

    await bot.send_message(chat_id=user_id,
                           text='test scheduler every 30 sec')