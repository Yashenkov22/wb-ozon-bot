import aiohttp

from aiogram import types, Bot

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from db.base import WbProduct, WbPunkt, User


async def push_check_wb_price(callback: types.CallbackQuery,
                              session: AsyncSession,
                              bot: Bot):
    print(f'фоновая задача {callback.from_user.id}')
    user_id = callback.from_user.id

    query = (
        select(
            WbProduct.short_link,
            WbPunkt.zone,
        )\
        .select_from(WbProduct)\
        .join(WbPunkt,
              WbProduct.wb_punkt_id == WbPunkt.id)\
        .join(User,
              WbProduct.user_id == User.tg_id)\
        .where(User.tg_id == user_id)
    )

    res = await session.execute(query)

    res = res.fetchall()

    if not res:
        return
    
    short_link, zone = res[0]

    async with aiohttp.ClientSession() as aiosession:
        # _url = f"http://172.18.0.2:8080/pickUpPoint/{lat}/{lon}"
        # response = await aiosession.get(url=_url)

        # res = await response.json()

        # deliveryRegions = res.get('deliveryRegions')

        # print(deliveryRegions)

        # del_zone = deliveryRegions[-1]

        _url = f"http://172.18.0.2:8080/product/{zone}/{short_link}"
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
