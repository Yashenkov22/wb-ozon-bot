from datetime import datetime
from typing import Any

import pytz

from aiogram import types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import update, select, and_, or_, insert
from sqlalchemy.ext.asyncio import AsyncSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.base import User, WbProduct, WbPunkt, OzonProduct, UserJob

from utils.scheduler import push_check_ozon_price, push_check_wb_price

from keyboards import add_back_btn, create_or_add_cancel_btn, create_photo_keyboard, create_remove_kb


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
                    'short_link': data.get('ozon_product_id'),
                    'actual_price': data.get('ozon_actual_price'),
                    'start_price': data.get('ozon_start_price'),
                    'percent': int(data.get('percent')),
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
                                second=30,
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
                                        second=30,
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

    msg: types.Message = data.get('msg')
    product_id, link, actaul_price, start_price, user_id, time_create, percent, job_id, photo_kb = item_constructor(data)

    # if not data.get('visited'):
    #     await state.update_data(visited=True)
    time_create: datetime
    moscow_tz = pytz.timezone('Europe/Moscow')
    moscow_time = time_create.astimezone(moscow_tz)

    waiting_price = actaul_price - ((actaul_price * percent) / 100)

    _text = f'Привет {user_id}\nТвой WB <a href="{link}">товар</a>\n\nНачальная цена: {start_price}\nАктуальная цена: {actaul_price}\nВыставленный процент: {percent}\nОжидаемая(или ниже) цена товара:{waiting_price}\nДата начала отслеживания: {moscow_time}'

    _kb = create_remove_kb(user_id=callback.from_user.id,
                           product_id=product_id,
                           marker='wb',
                           job_id=job_id,
                           _kb=photo_kb)
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
    product_idx = data['_idx_product']
    wb_product_list = data['wb_product_list']
    print('wb_product list', wb_product_list, 'idx', product_idx)
    kb_init: str
    
    if len(wb_product_list) == 1:
        kb_init = 'one'
    else:
        if product_idx == 0:
            kb_init = 'start'
        elif product_idx < len(wb_product_list)-1:
            kb_init = 'mid'
        else:
            kb_init = 'end'

    photo_kb = create_photo_keyboard(kb_init)
    _product = wb_product_list[product_idx]
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