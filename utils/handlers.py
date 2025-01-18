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

from db.base import User, WbProduct, WbPunkt, OzonProduct, UserJob

from utils.scheduler import push_check_ozon_price, push_check_wb_price

from keyboards import (add_back_btn,
                       create_or_add_cancel_btn,
                       create_photo_keyboard, create_product_list_kb,
                       create_remove_kb,
                       add_cancel_btn_to_photo_keyboard)


async def check_user_last_message_time(user_id: int,
                                       session: AsyncSession):
    query = (
        select(
            User
        )\
        .where(User.tg_id == user_id)
    )

    res = await session.execute(query)

    user = res.scalar_one_or_none()

    if user:
        moscow_tz = pytz.timezone('Europe/Moscow')
        _now = datetime.now()
        moscow_time = _now.astimezone(moscow_tz)
        _time_delta = moscow_time - timedelta(seconds=2)

        if user.last_action_time is not None \
            and user.last_action_time >= _time_delta:
            return 'percent'
        else:
            await sleep(1)
            return 'link'
        

async def validate_link(message: types.Message,
                        state: FSMContext,
                        session: AsyncSession):
    _idx = message.text.find('https')

    if _idx > 0:
        link = message.text[_idx:]
    else:
        return
    
    if link.startswith('https://ozon'):
        query = (
            update(
                User
            )\
            .values(last_action_time=datetime.now(),
                    last_action='ozon')\
            .where(User.tg_id == message.from_user.id)
        )

        await session.execute(query)
        await session.commit()
        pass
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
    elif link.startswith('https://www.wildberries'):
        query = (
            update(
                User
            )\
            .values(lact_action_time=datetime.now(),
                    last_action='wb')\
            .where(User.tg_id == message.from_user.id)
        )

        await session.execute(query)
        await session.commit()
        pass
    else:
        pass



async def clear_state_and_redirect_to_start(message: types.Message | types.CallbackQuery,
                                            state: FSMContext,
                                            bot: Bot):
    await state.clear()

    _kb = add_back_btn(InlineKeyboardBuilder())

    _text = 'Что пошло не так\nВернитесь в главное меню и попробуйте еще раз'

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
                    'percent': int(data.get('percent')),
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

                job = scheduler.add_job(push_check_ozon_price,
                                trigger='cron',
                                minute=1,
                                jobstore='sqlalchemy',
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
                            'percent': float(data.get('percent')),
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
                        job = scheduler.add_job(push_check_wb_price,
                                        trigger='cron',
                                        minute=1,
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
    product_id, link, actaul_price, start_price, user_id, time_create, percent, job_id = _product

    return (
        product_id,
        link,
        actaul_price,
        start_price,
        user_id,
        time_create,
        percent,
        job_id,
        photo_kb,
    )



async def show_item_list(callback: types.CallbackQuery,
                         state: FSMContext,
                         bot: Bot):
    data = await state.get_data()

    marker = data.get('action')

    msg: types.Message = data.get('msg')

    # product_idx = data.get(f'{marker}_product_idx')
    product_list = data.get(f'{marker}_product_list')

    _kb = create_product_list_kb(callback.from_user.id,
                                 product_list,
                                 marker)
    _kb = create_or_add_cancel_btn(_kb)
    
    _text = f'Ваши {marker} товары'
    
    if msg:
        await msg.edit_text(text=_text,
                            reply_markup=_kb.as_markup())
    else:
        await bot.send_message(chat_id=callback.from_user.id,
                               text=_text,
                               reply_markup=_kb.as_markup())
    
