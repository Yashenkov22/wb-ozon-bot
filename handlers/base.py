import os
import json
import re

from math import ceil

import aiohttp

import pytz

from datetime import datetime, timedelta

from aiogram import Router, types, Bot, F
from aiogram.types import BufferedInputFile, URLInputFile
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from sqlalchemy.orm import Session, joinedload, sessionmaker
from sqlalchemy import and_, insert, select, update, or_, delete, func, Integer, Float
from sqlalchemy.sql.expression import cast

from sqlalchemy.ext.asyncio import AsyncSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BEARER_TOKEN, FEEDBACK_REASON_PREFIX, DEV_ID

from keyboards import (create_or_add_exit_btn,
                       create_remove_kb,
                       create_start_kb,
                       create_or_add_cancel_btn,
                       create_done_kb,
                       create_wb_start_kb,
                       add_back_btn,
                       create_bot_start_kb,
                       create_remove_and_edit_sale_kb,
                       create_reply_start_kb)

from states import AnyProductStates, EditSale, SwiftSepaStates, ProductStates, OzonProduct

from utils.handlers import (DEFAULT_PAGE_ELEMENT_COUNT,
                            check_input_link,
                            check_user_last_message_time,
                            generate_pretty_amount,
                            save_data_to_storage,
                            check_user,
                            show_item,
                            save_product,
                            show_product_list)
from utils.scheduler import test_scheduler

from db.base import OzonProduct as OzonProductModel, User, Base, UserJob, WbProduct


main_router = Router()

start_text = '💱<b>Добро пожаловать в MoneySwap!</b>\n\nНаш бот поможет найти лучшую сделку под вашу задачу 💸\n\n👉🏻 <b>Чтобы начать поиск</b>, выберите категорию “безналичные”, “наличные” или “Swift/Sepa” и нажмите на нужную кнопку ниже.\n\nЕсли есть какие-то вопросы, обращайтесь <a href="https://t.me/MoneySwap_support">Support</a> или <a href="https://t.me/moneyswap_admin">Admin</a>. Мы всегда готовы вам помочь!'

moscow_tz = pytz.timezone('Europe/Moscow')


@main_router.message(Command('start'))
async def start(message: types.Message | types.CallbackQuery,
                state: FSMContext,
                session: AsyncSession,
                bot: Bot,
                scheduler: AsyncIOScheduler):
    _message = message
    
    await state.clear()
    
    await check_user(message,
                     session)
    
    # scheduler.print_jobs()
    
    await state.update_data(action=None)

    if isinstance(message, types.CallbackQuery):
        message = message.message

    _kb = create_start_kb()
    msg = await bot.send_message(text='Привет.\nЭто тестовые WB и OZON боты.',
                                chat_id=_message.from_user.id,
                                reply_markup=_kb.as_markup())
    
    await state.update_data(msg=(msg.chat.id, msg.message_id))

    try:
        await message.delete()
        
        if isinstance(_message, types.CallbackQuery):
            await _message.answer()

    except Exception as ex:
        print(ex)


@main_router.message(Command('start1'))
async def start1(message: types.Message | types.CallbackQuery,
                state: FSMContext,
                session: AsyncSession,
                bot: Bot,
                scheduler: AsyncIOScheduler):
    _message = message
    
    await state.clear()
    
    await check_user(message,
                     session)
    
    # scheduler.print_jobs()
    
    await state.update_data(action=None)

    if isinstance(message, types.CallbackQuery):
        message = message.message

    _kb = create_reply_start_kb()
    await bot.send_message(text='Главное меню',
                                chat_id=_message.from_user.id,
                                reply_markup=_kb.as_markup(resize_keyboard=True))
    
    # await state.update_data(msg=(msg.chat.id, msg.message_id))

    try:
        await message.delete()
        
        if isinstance(_message, types.CallbackQuery):
            await _message.answer()

    except Exception as ex:
        print(ex)


@main_router.message(F.text == 'Добавить товар')
async def add_any_product(message: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    await state.set_state(AnyProductStates.link)
    
    data = await state.get_data()

    # msg: tuple = data.get('msg')
    _text = 'Отправьте ссылку на товар'

    _kb = create_or_add_exit_btn()

    # if msg:
    add_msg = await bot.send_message(text=_text,
                           chat_id=message.from_user.id,
                           reply_markup=_kb.as_markup())
    
    await state.update_data(add_msg=(add_msg.chat.id, add_msg.message_id))
    # else:
    #     await callback.message.answer(text=_text,
    #                          reply_markup=_kb.as_markup())
    try:
        await message.delete()
    except Exception:
        pass


@main_router.message(AnyProductStates.link)
async def any_product_proccess(message: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    data = await state.get_data()

    add_msg: tuple = data.get('add_msg')

    print('add msg', add_msg)

    _message_text = message.text.strip().split()

    _name = link = None

    if len(_message_text) > 1:
        *_name, link = _message_text
        _name = ' '.join(_name)
    else:
        # if not message_text.isdigit():
        link = message.text.strip()

    check_link = check_input_link(link) # None or Literal['WB', 'OZON']

    if check_link:

        user_data = {
            'msg': (message.chat.id, message.message_id),
            'name': _name,
            'link': link,
        }
        find_in_db = await save_product(user_data=user_data,
                                        session=session,
                                        scheduler=scheduler)
        
        if find_in_db:
            _text = f'{check_link} Товар уже был в Вашем списке или ошибка'
        else:
            _text = f'{check_link} Товар успешно добавлен!'
            
        await message.answer(text=_text)
    else:
        await message.answer(text='Невалидная ссылка')
    
    try:
        await state.set_state()
        await bot.delete_message(chat_id=add_msg[0],
                                 message_id=add_msg[-1])
        await message.delete()
    except Exception as ex:
        print(ex)
        pass
    

@main_router.message(F.text == 'Посмотреть товары')
async def get_all_products_by_user(message: types.Message | types.CallbackQuery,
                                state: FSMContext,
                                session: AsyncSession,
                                bot: Bot,
                                scheduler: AsyncIOScheduler):
    # DEFAULT_PAGE_ELEMENT_COUNT = 5
    # await state.set_state(AnyProductStates.link)
    await state.update_data(view_product_dict=None)
    
    data = await state.get_data()

    subquery_wb = (
        select(UserJob.job_id,
               UserJob.user_id,
               UserJob.product_id)
        .where(UserJob.user_id == message.from_user.id)
    ).subquery()

    wb_query = (
        select(WbProduct.id,
               WbProduct.link,
            #    WbProduct.actual_price,
               cast(WbProduct.actual_price, Integer).label('actual_price'),
            #    WbProduct.start_price,
               cast(WbProduct.start_price, Integer).label('start_price'),
               WbProduct.user_id,
            #    WbProduct.time_create,
            #    func.extract('epoch', WbProduct.time_create).label('time_create'),
               cast(func.extract('epoch', OzonProductModel.time_create), Float).label('time_create'),
               func.text('wb').label('product_marker'),
               WbProduct.name,
               WbProduct.sale,
               subquery_wb.c.job_id)\
        .select_from(WbProduct)\
        .join(User,
              WbProduct.user_id == User.tg_id)\
        .join(UserJob,
              UserJob.user_id == User.tg_id)\
        .outerjoin(subquery_wb,
                   subquery_wb.c.product_id == WbProduct.id)\
        .where(User.tg_id == message.from_user.id)\
        .distinct(WbProduct.id)
    )

    subquery_ozon = (
        select(UserJob.job_id,
               UserJob.user_id,
               UserJob.product_id)
        .where(UserJob.user_id == message.from_user.id)
    ).subquery()

    ozon_query = (
        select(
            OzonProductModel.id,
            OzonProductModel.link,
            # OzonProductModel.actual_price,
            cast(OzonProductModel.actual_price, Integer).label('actual_price'),
            # OzonProductModel.start_price,
            cast(OzonProductModel.start_price, Integer).label('start_price'),
            OzonProductModel.user_id,
            # OzonProductModel.time_create,
            # func.extract('epoch', OzonProductModel.time_create).label('time_create'),
            cast(func.extract('epoch', OzonProductModel.time_create), Float).label('time_create'),
            func.text('ozon').label('product_marker'),
            OzonProductModel.name,
            OzonProductModel.sale,
            subquery_ozon.c.job_id)\
        .select_from(OzonProductModel)\
        .join(User,
              OzonProductModel.user_id == User.tg_id)\
        .join(UserJob,
              UserJob.user_id == User.tg_id)\
        .outerjoin(subquery_ozon,
                   subquery_ozon.c.product_id == OzonProductModel.id)\
        .where(User.tg_id == message.from_user.id)\
        .distinct(OzonProductModel.id)
    )

    async with session as _session:
        res = await _session.execute(wb_query.union(ozon_query))

    product_list = res.fetchall()

    if not product_list:
        await message.answer('Нет добавленных продуктов')
        return

    product_list = sorted(map(lambda el: tuple(el), product_list),
                          key=lambda el: el[5],   # sort by time_create field
                          reverse=True)           # order by desc

    len_product_list = len(product_list)
    pages = ceil(len_product_list / DEFAULT_PAGE_ELEMENT_COUNT)
    current_page = 1

    view_product_dict = {
        'len_product_list': len_product_list,
        'pages': pages,
        'current_page': current_page,
        'product_list': product_list,
    }

    print(view_product_dict)

    await show_product_list(view_product_dict,
                            message.from_user.id,
                            state)
    # msg: tuple = data.get('msg')
    # _text = 'Отправьте ссылку на товар'

    # _kb = create_or_add_exit_btn()

    # # if msg:
    # add_msg = await bot.send_message(text=_text,
    #                        chat_id=message.from_user.id,
    #                        reply_markup=_kb.as_markup())
    
    # await state.update_data(add_msg=(add_msg.chat.id, add_msg.message_id))
    # # else:
    # #     await callback.message.answer(text=_text,
    # #                          reply_markup=_kb.as_markup())
    try:
        await message.delete()
    except Exception:
        pass


@main_router.callback_query(F.data.startswith('page'))
async def callback_done(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler):
    callback_data = callback.data.split('_')[-1]
    
    data = await state.get_data()
    
    product_dict = data.get('view_product_dict')
    # await state.update_data(view_product_dict=None)
    if not product_dict:
        await callback.answer(text='Ошибка',
                              show_alert=True)
    if callback == 'next':
        product_dict['current_page'] += 1
    else:
        product_dict['current_page'] -= 1

    await show_product_list(product_dict,
                            callback.from_user.id,
                            state)
    
    # pass


@main_router.message(Command('test_ozon_pr'))
async def test_db_ozon(message: types.Message,
                       state: FSMContext,
                       session: AsyncSession,
                       bot: Bot):
    user_id = message.from_user.id

    query = (
        select(
            OzonProductModel.link,
            OzonProductModel.actual_price,
            OzonProductModel.start_price,
            OzonProductModel.time_create,
            OzonProductModel.user_id)\
        .join(User,
              OzonProductModel.user_id == User.tg_id)\
        .where(User.tg_id == user_id)
    )
    # async with session as session:
    ozon_product = await session.execute(query)

    ozon_product = ozon_product.fetchall()

    ozon_product = ozon_product[0]

    link, actual_price, basic_price, time_create, _user_id = ozon_product

    # ozon_product = ozon_product[0]

    # print('ozon product', ozon_product.user_id, ozon_product.user, ozon_product.link)

    if ozon_product:
        await message.answer(f'Привет {_user_id}\nТвой товар\n{link}\nОсновная цена: {basic_price}\nАктуальная цена: {actual_price}\nДата создания отслеживания: {time_create}')
    else:
        await message.answer('не получилось')


@main_router.callback_query(F.data.startswith('bot'))
async def redirect_to_(callback: types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler,
                        marker: str = None):
    scheduler.print_jobs()

    # UPDATE SCHEDULER TASK
    # if callback.from_user.id == DEV_ID:   
    #     _jobs = scheduler.get_jobs()
    #     for _job in _jobs:
    #         pass

    if not marker:
        marker = callback.data.split('_')[-1]

        if marker == 'cancel':
            await start(callback,
                        state,
                        session,
                        bot,
                        scheduler)
            try:
                await callback.message.delete()
            except Exception:
                pass
            return

    await state.update_data(action=marker)

    data = await state.get_data()
    msg = data.get('msg')

    # JobModel = Base.metadata.tables['apscheduler_jobs']
    JobModel = Base.classes.apscheduler_jobs


    print(JobModel.__dict__)
###

    query = (
        select(JobModel.id)
    )

    res = await session.execute(query)
    res = res.fetchall()

    for r in res:
        print(r)
###
    _text = f'{marker.upper()} бот\nВыберите действие'

    _kb = create_bot_start_kb(marker=marker)

    _kb = add_back_btn(_kb)

    if msg:
        try:
            await bot.edit_message_text(text=_text,
                                        chat_id=callback.message.chat.id,
                                        message_id=msg[-1],
                                        reply_markup=_kb.as_markup())
        except Exception:
            await bot.send_message(chat_id=callback.message.chat.id,
                                text=_text,
                                reply_markup=_kb.as_markup())
    else:
        await bot.send_message(chat_id=callback.message.chat.id,
                               text=_text,
                               reply_markup=_kb.as_markup())


@main_router.callback_query(F.data == 'cancel')
async def callback_cancel(callback: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    # await start(callback,
    #             state,
    #             bot)
    data = await state.get_data()

    action = data.get('action')

    await redirect_to_(callback,
                       state,
                       session,
                       bot,
                       scheduler,
                       marker=action)
    
@main_router.callback_query(F.data == 'exit')
async def callback_to_main(callback: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    await state.set_state()
    try:
        await callback.message.delete()
    except Exception:
        pass
    

@main_router.callback_query(F.data == 'to_main')
async def callback_to_main(callback: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    # callback_data = callback.data.split('_')[-1]

    # await redirect_to_(callback,
    #               state,
    #               bot,
    #               marker='wb')
    await start(callback,
                state,
                session,
                bot,
                scheduler)
    

@main_router.callback_query(F.data.startswith('done'))
async def callback_done(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler):
    data = await state.get_data()

    action = data.get('action')
    msg = data.get('msg')

    callback_data = callback.data.split('__')[-1]

    _text = await save_data_to_storage(callback,
                                        state,
                                        session,
                                        bot,
                                        scheduler,
                                        callback_data)
    
    await state.clear()

    if msg:
        await state.update_data(msg=msg)
    
    await callback.answer(text=_text,
                          show_alert=True)
    
    await redirect_to_(callback,
                       state,
                       session,
                       bot,
                       scheduler,
                       marker=action)
    

@main_router.callback_query(F.data == 'close')
async def callback_close(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler):
    try:
        await callback.message.delete()
    except Exception as ex:
        print(ex)
    # data = await state.get_data()

    # action = data.get('action')
    # msg = data.get('msg')

    # callback_data = callback.data.split('__')[-1]

    # _text = await save_data_to_storage(callback,
    #                                     state,
    #                                     session,
    #                                     bot,
    #                                     scheduler,
    #                                     callback_data)
    
    # await state.clear()

    # if msg:
    #     await state.update_data(msg=msg)
    
    # await callback.answer(text=_text,
    #                       show_alert=True)
    
    # await redirect_to_(callback,
    #                    state,
    #                    session,
    #                    bot,
    #                    scheduler,
    #                    marker=action)
    
    # await callback.answer(text='Пункт выдачи добавлен.',
    #                       show_alert=True)
    # await start(callback,
    #             state,
    #             session,
    #             bot,
    #             scheduler)

@main_router.callback_query(F.data.startswith('delete'))
async def delete_callback(callback: types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler):
    with_redirect = True
    
    _callback_data = callback.data.split('_')

    callback_prefix = _callback_data[0]

    if callback_prefix.endswith('rd'):
        with_redirect = False

    callback_data = _callback_data[1:]
    marker, user_id, product_id, job_id = callback_data

    match marker:
        case 'wb':
            query1 = (
                delete(
                    UserJob
                )\
                .where(
                    and_(
                        UserJob.user_id == int(user_id),
                        UserJob.product_id == int(product_id),
                    )
                )
            )
            query2 = (
                delete(
                    WbProduct
                )\
                .where(
                    and_(
                        # WbProduct.user_id == int(user_id),
                        WbProduct.id == int(product_id),
                    )
                )
            )
            async with session.begin():
                await session.execute(query1)
                await session.execute(query2)
                try:
                    await session.commit()
                    # job = scheduler.get_job(job_id=job_id,
                    #                         jobstore='sqlalchemy')
                    # print('JOB', job)

                    
                    scheduler.remove_job(job_id=job_id,
                                         jobstore='sqlalchemy')
                except Exception as ex:
                    print(ex)
                    await session.rollback()
                else:
                    await callback.answer('Товар успешно удален',
                                          show_alert=True)
            
            if with_redirect:
                await redirect_to_(callback,
                                state,
                                session,
                                bot,
                                scheduler,
                                marker=marker)
            else:
                try:
                    await callback.message.delete()
                except Exception as ex:
                    print(ex)
            pass
        case 'ozon':
            query1 = (
                delete(
                    UserJob
                )\
                .where(
                    and_(
                        UserJob.user_id == int(user_id),
                        UserJob.product_id == int(product_id),
                    )
                )
            )
            query2 = (
                delete(
                    OzonProductModel
                )\
                .where(
                    and_(
                        # WbProduct.user_id == int(user_id),
                        OzonProductModel.id == int(product_id),
                    )
                )
            )
            async with session.begin():
                await session.execute(query1)
                await session.execute(query2)
                try:
                    await session.commit()
                    # job = scheduler.get_job(job_id=job_id,
                    #                         jobstore='sqlalchemy')
                    # print('JOB', job)

                    
                    scheduler.remove_job(job_id=job_id,
                                         jobstore='sqlalchemy')
                except Exception as ex:
                    print(ex)
                    await session.rollback()
                else:
                    await callback.answer('Товар успешно удален',
                                          show_alert=True)
            
            if with_redirect:
                await redirect_to_(callback,
                                state,
                                session,
                                bot,
                                scheduler,
                                marker=marker)
            else:
                try:
                    await callback.message.delete()
                except Exception as ex:
                    print(ex)


@main_router.callback_query(F.data.startswith('edit.sale'))
async def edit_sale_callback(callback: types.CallbackQuery,
                          state: FSMContext,
                          session: AsyncSession,
                          bot: Bot,
                          scheduler: AsyncIOScheduler):
    data = await state.get_data()

    _sale_data = data.get('sale_data')

    link = _sale_data.get('link')
    sale = _sale_data.get('sale')

    with_redirect = True

    callback_data = callback.data.split('_')
    callback_prefix = callback_data[0]

    # product_model = OzonProductModel if marker == 'ozon' else WbProduct

    marker, user_id, product_id = callback_data[1:]

    if callback_prefix.endswith('rd'):
        with_redirect = False

    # query = (
    #     select(
    #         product_model.sale
    #     )\
    #     .where(
    #         and_(
    #             product_model.id == product_id,
    #             product_model.user_id == user_id,
    #         )
    #     )
    # )

    # async with session as _session:
    #     res = await _session.execute(query)

    #     sale = res.scalar_one_or_none()

    # if not sale:
    #     await callback.answer(text='Не получилось найти товар.\nПопробуйте еще раз',
    #                           show_alert=True)
    #     return

    await state.update_data(
        sale_data={
            'user_id': user_id,
            'product_id': product_id,
            'marker': marker,
            'link': link,
            'sale': sale,
        }
        )
    await state.set_state(EditSale.new_sale)

    _kb = create_or_add_cancel_btn()

    await bot.edit_message_text(text=f'<b>Установленная скидка на Ваш {marker.upper()} <a href="{link}">товар</a> {sale}</b>\n\nУкажите новую скидку <b>как число</b> в следующем сообщении',
                                chat_id=callback.from_user.id,
                                message_id=callback.message.message_id,
                                reply_markup=_kb.as_markup())
    await callback.answer()
    pass


@main_router.message(EditSale.new_sale)
async def edit_sale_proccess(message: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    new_sale = message.text.strip()

    if not new_sale.isdigit():
        await message.answer(text=f'Невалидные данные\nОжидается число, передано: {new_sale}')
        return
    
    data = await state.get_data()

    msg: tuple = data.get('msg')

    sale_data: dict = data.get('sale_data')

    if not sale_data:
        await message.answer('Ошибка')
        return
    
    user_id = sale_data.get('user_id')
    product_id = sale_data.get('product_id')
    marker = sale_data.get('marker')
    
    product_model = OzonProductModel if marker == 'ozon' else WbProduct

    query = (
        update(
            product_model
        )\
        .values(sale=float(new_sale))\
        .where(
            and_(
                product_model.id == int(product_id),
                product_model.user_id == int(user_id)
            )
        )
    )

    async with session as _session:
        try:
            await _session.execute(query)
            await _session.commit()
        except Exception as ex:
            print(ex)
            await session.rollback()
            await message.answer('Не удалось обновить скидку')
        else:
            # await message.answer('Скидка обновлена')
            _kb = create_or_add_cancel_btn()
            await bot.edit_message_text(text='Скидка обновлена',
                                        chat_id=msg[0],
                                        message_id=msg[-1],
                                        reply_markup=_kb.as_markup())
            
            await state.update_data(sale_data=None)
    try:
        await message.delete()
    except Exception:
        pass


@main_router.callback_query(F.data.startswith('product'))
async def init_current_item(callback: types.CallbackQuery,
                            state: FSMContext):
    action = callback.data.split('_')[-1]
    
    data = await state.get_data()
    marker = data.get('action')

    product_idx = data.get(f'{marker}_product_idx')
    print('idx from callback',product_idx)
    match action:
        case 'next':
            # await state.update_data(_idx_product=product_idx+1)
            await state.update_data(data={f'{marker}_product_idx': product_idx+1})
        case 'prev':
            await state.update_data(data={f'{marker}_product_idx': product_idx-1})
    await show_item(callback, state)
            

@main_router.callback_query(F.data.startswith('view-product1'))
async def view_product1(callback: types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler,
                        marker: str = None):
    data = await state.get_data()

    list_msg: tuple = data.get('list_msg')

    callback_data = callback.data.split('_')[1:]

    user_id, marker, product_id = callback_data

    match marker:
        case 'wb':
            # pass
            subquery = (
                select(UserJob.job_id,
                    UserJob.user_id,
                    UserJob.product_id)
                .where(UserJob.user_id == callback.from_user.id)
            ).subquery()

            query = (
                select(WbProduct.id,
                    WbProduct.link,
                    WbProduct.actual_price,
                    WbProduct.start_price,
                    WbProduct.user_id,
                    WbProduct.time_create,
                    WbProduct.name,
                    WbProduct.sale,
                    func.text('WB').label('product_marker'),
                    subquery.c.job_id)\
                .select_from(WbProduct)\
                .join(User,
                    WbProduct.user_id == User.tg_id)\
                .join(UserJob,
                    UserJob.user_id == User.tg_id)\
                .outerjoin(subquery,
                        subquery.c.product_id == WbProduct.id)\
                .where(
                    and_(
                        User.tg_id == callback.from_user.id,
                        WbProduct.id == int(product_id),
                        )
                    )\
                .distinct(WbProduct.id)
            )

            async with session as _session:
                res = await _session.execute(query)

                _data = res.fetchall()
            
            if _data:
                _product = _data[0]
                product_id, link, actaul_price, start_price, user_id, time_create, name, sale, product_marker, job_id = _product

        case 'ozon':
            # pass
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
                    func.text('OZON').label('product_marker'),
                    subquery.c.job_id)\
                .select_from(OzonProductModel)\
                .join(User,
                    OzonProductModel.user_id == User.tg_id)\
                .join(UserJob,
                    UserJob.user_id == User.tg_id)\
                .outerjoin(subquery,
                        subquery.c.product_id == OzonProductModel.id)\
                .where(
                    and_(
                        User.tg_id == callback.from_user.id,
                        OzonProductModel.id == int(product_id),
                        )
                    )\
                .distinct(OzonProductModel.id)
            )

            async with session as _session:
                res = await _session.execute(query)

                _data = res.fetchall()

            if _data:
                len(_data)
                _product = _data[0]
                product_id, link, actaul_price, start_price, user_id, time_create, name, sale, product_marker, job_id = _product


    time_create: datetime
    moscow_tz = pytz.timezone('Europe/Moscow')
    moscow_time = time_create.astimezone(moscow_tz)
    
    # if percent:
    #     waiting_price = start_price - ((start_price * percent) / 100)
    waiting_price = start_price - sale

    _text_start_price = generate_pretty_amount(start_price)
    _text_product_price = generate_pretty_amount(actaul_price)

    _text_sale = generate_pretty_amount(sale)
    _text_price_with_sale = generate_pretty_amount((start_price - sale))
    # _text_basic_price = generate_pretty_amount(_d.get("price", 0))

    # _text = f'Привет {user_id}\nТвой {marker} <a href="{link}">товар</a>\n\nНачальная цена: {start_price}\nАктуальная цена: {actaul_price}\nУстановленная скидка: {sale}\nОжидаемая(или ниже) цена товара:{waiting_price}\nДата начала отслеживания: {moscow_time}'
    
    _text = f'Название: <a href="{link}">{name}</a>\nМаркетплейс: {product_marker}\n\nНачальная цена: {_text_start_price}\nАктуальная цена: {_text_product_price}\n\nОтслеживается изменение цены на: {_text_sale}\nОжидаемая цена: {_text_price_with_sale}'
    # else:
    #     _text = f'Привет {user_id}\nТвой {marker} <a href="{link}">товар</a>\n\nНачальная цена: {start_price}\nАктуальная цена: {actaul_price}\n\nДата начала отслеживания: {moscow_time}'

    # _kb = add_cancel_btn_to_photo_keyboard(photo_kb)

    # _kb = create_remove_kb(user_id=callback.from_user.id,
    #                     product_id=product_id,
    #                     marker=marker,
    #                     job_id=job_id)
    # print(link)
    await state.update_data(
        sale_data={
            'link': link,
            'sale': sale,
        }
    )

    _kb = create_remove_and_edit_sale_kb(user_id=callback.from_user.id,
                                         product_id=product_id,
                                         marker=marker,
                                         job_id=job_id)
    # _kb = create_or_add_cancel_btn(_kb)
    _kb = create_or_add_exit_btn(_kb)

    if list_msg:
        await bot.edit_message_text(chat_id=list_msg[0],
                                    message_id=list_msg[-1],
                                    text=_text,
                                    reply_markup=_kb.as_markup())
    else:
        await bot.send_message(chat_id=callback.from_user.id,
                               text=_text,
                               reply_markup=_kb.as_markup())


@main_router.callback_query(F.data.startswith('view-product'))
async def view_product(callback: types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler,
                        marker: str = None):
    data = await state.get_data()

    msg: tuple = data.get('msg')

    callback_data = callback.data.split('_')[1:]

    user_id, marker, product_id = callback_data

    match marker:
        case 'wb':
            # pass
            subquery = (
                select(UserJob.job_id,
                    UserJob.user_id,
                    UserJob.product_id)
                .where(UserJob.user_id == callback.from_user.id)
            ).subquery()

            query = (
                select(WbProduct.id,
                    WbProduct.link,
                    WbProduct.actual_price,
                    WbProduct.start_price,
                    WbProduct.user_id,
                    WbProduct.time_create,
                    WbProduct.name,
                    WbProduct.sale,
                    func.text('WB').label('product_marker'),
                    subquery.c.job_id)\
                .select_from(WbProduct)\
                .join(User,
                    WbProduct.user_id == User.tg_id)\
                .join(UserJob,
                    UserJob.user_id == User.tg_id)\
                .outerjoin(subquery,
                        subquery.c.product_id == WbProduct.id)\
                .where(
                    and_(
                        User.tg_id == callback.from_user.id,
                        WbProduct.id == int(product_id),
                        )
                    )\
                .distinct(WbProduct.id)
            )

            async with session as _session:
                res = await _session.execute(query)

                _data = res.fetchall()
            
            if _data:
                _product = _data[0]
                product_id, link, actaul_price, start_price, user_id, time_create, name, sale, product_marker, job_id = _product

        case 'ozon':
            # pass
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
                    func.text('OZON').label('product_marker'),
                    subquery.c.job_id)\
                .select_from(OzonProductModel)\
                .join(User,
                    OzonProductModel.user_id == User.tg_id)\
                .join(UserJob,
                    UserJob.user_id == User.tg_id)\
                .outerjoin(subquery,
                        subquery.c.product_id == OzonProductModel.id)\
                .where(
                    and_(
                        User.tg_id == callback.from_user.id,
                        OzonProductModel.id == int(product_id),
                        )
                    )\
                .distinct(OzonProductModel.id)
            )

            async with session as _session:
                res = await _session.execute(query)

                _data = res.fetchall()

            if _data:
                len(_data)
                _product = _data[0]
                product_id, link, actaul_price, start_price, user_id, time_create, name, sale, product_marker, job_id = _product


    time_create: datetime
    moscow_tz = pytz.timezone('Europe/Moscow')
    moscow_time = time_create.astimezone(moscow_tz)
    
    # if percent:
    #     waiting_price = start_price - ((start_price * percent) / 100)
    waiting_price = start_price - sale

    _text_start_price = generate_pretty_amount(start_price)
    _text_product_price = generate_pretty_amount(actaul_price)

    _text_sale = generate_pretty_amount(sale)
    _text_price_with_sale = generate_pretty_amount((start_price - sale))
    # _text_basic_price = generate_pretty_amount(_d.get("price", 0))

    # _text = f'Привет {user_id}\nТвой {marker} <a href="{link}">товар</a>\n\nНачальная цена: {start_price}\nАктуальная цена: {actaul_price}\nУстановленная скидка: {sale}\nОжидаемая(или ниже) цена товара:{waiting_price}\nДата начала отслеживания: {moscow_time}'
    
    _text = f'Название: <a href="{link}">{name}</a>\nМаркетплейс: {product_marker}\n\nНачальная цена: {_text_start_price}\nАктуальная цена: {_text_product_price}\n\nОтслеживается изменение цены на: {_text_sale}\nОжидаемая цена: {_text_price_with_sale}'
    # else:
    #     _text = f'Привет {user_id}\nТвой {marker} <a href="{link}">товар</a>\n\nНачальная цена: {start_price}\nАктуальная цена: {actaul_price}\n\nДата начала отслеживания: {moscow_time}'

    # _kb = add_cancel_btn_to_photo_keyboard(photo_kb)

    # _kb = create_remove_kb(user_id=callback.from_user.id,
    #                     product_id=product_id,
    #                     marker=marker,
    #                     job_id=job_id)
    # print(link)
    await state.update_data(
        sale_data={
            'link': link,
            'sale': sale,
        }
    )

    _kb = create_remove_and_edit_sale_kb(user_id=callback.from_user.id,
                                         product_id=product_id,
                                         marker=marker,
                                         job_id=job_id)
    _kb = create_or_add_cancel_btn(_kb)

    if msg:
        await bot.edit_message_text(chat_id=msg[0],
                                    message_id=msg[-1],
                                    text=_text,
                                    reply_markup=_kb.as_markup())
# _callback_data = f'view-product_{user_id}_{marker}_{product_id}'


@main_router.callback_query(F.data == 'remove_all_products')
async def remove_all_ozon_product_by_user(callback: types.CallbackQuery,
                                            state: FSMContext,
                                            session: AsyncSession,
                                            scheduler: AsyncIOScheduler):
    try:
        query = select(
            OzonProductModel.id,
            # OzonProductModel.user_id,
        )\
        .where(OzonProductModel.user_id == callback.from_user.id)

        async with session as _session:
            res = await _session.execute(query)

            product_ids = res.scalars().all()

        # user_ids = []
        # product_ids = []

        if not product_ids:
            await callback.answer(text='Нет товаров на удаление',
                                  show_alert=True)
            return

        # for record in res:
        #     _id, _product_id = record
        #     user_ids.append(_id)
        #     product_ids.append(_product_id)

        user_job_query = (
            select(
                UserJob.job_id,
            )\
            .where(
                and_(
                    UserJob.user_id == callback.from_user.id,
                    UserJob.product_id.in_(product_ids),
                    UserJob.product_marker == 'ozon_product',
                )
            )
        )

        async with session as _session:
            res = await _session.execute(user_job_query)

            job_ids = res.scalars().all()

            print(job_ids)

        del_query_1 = (
            delete(
                UserJob
            )\
            .where(
                and_(
                    UserJob.user_id == callback.from_user.id,
                    UserJob.product_id.in_(product_ids),
                    UserJob.product_marker == 'ozon',
                )
            )
        )

        del_query_2 = (
            delete(
                OzonProductModel
            )\
            .where(OzonProductModel.id.in_(product_ids))
        )

        async with session as _session:
            await _session.execute(del_query_1)
            await _session.execute(del_query_2)

            await _session.commit()
        
        for job_id in job_ids:
            scheduler.remove_job(job_id=job_id,
                                    jobstore='sqlalchemy')
            
            
    except Exception as ex:
        print(ex)
        await callback.answer(text='Не получилось',
                              show_alert=True)
    else:
        await callback.answer(text='Товары Озон успешно удалены',
                              show_alert=True)
            
            


@main_router.message()
async def any_input(message: types.Message,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot,
                    scheduler: AsyncIOScheduler):
    _message_text = message.text.strip().split()

    _name = link = None

    if len(_message_text) > 1:
        *_name, link = _message_text
        _name = ' '.join(_name)
    else:
        # if not message_text.isdigit():
        link = message.text.strip()

    check_link = check_input_link(link)

    if check_link:

        user_data = {
            'msg': (message.chat.id, message.message_id),
            'name': _name,
            'link': link,
        }
        find_in_db = await save_product(user_data=user_data,
                                        session=session,
                                        scheduler=scheduler)
        
        if find_in_db:
            _text = 'Товар уже был в Вашем списке или ошибка'
        else:
            _text = 'Товар успешно добавлен!'
            
            await message.answer(text=_text)
    else:
        await message.answer(text='Невалидная ссылка')
    
    # await state.set_state()
    await message.delete()