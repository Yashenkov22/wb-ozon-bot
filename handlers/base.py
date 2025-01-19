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
from sqlalchemy import and_, insert, select, update, or_, delete

from sqlalchemy.ext.asyncio import AsyncSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BEARER_TOKEN, FEEDBACK_REASON_PREFIX, DEV_ID

from keyboards import (create_remove_kb, create_start_kb,
                       create_or_add_cancel_btn,
                       create_done_kb,
                       create_wb_start_kb,
                       add_back_btn,
                       create_bot_start_kb)

from states import SwiftSepaStates, ProductStates, OzonProduct

from utils.handlers import check_user_last_message_time, save_data_to_storage, check_user, show_item, validate_link
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
    
    # logger.info('hi')
    # print(scheduler)
    # print(type(scheduler))
    scheduler.print_jobs()

    # _product_name = 'wb'

    # _product_id = 'test_product_id'

    # job_name = f'{message.from_user.id}_{_product_name}_{_product_id}'

    # try:
    #     _job = scheduler.add_job(test_scheduler,
    #                             'cron',
    #                             second=30,
    #                             args=(message.from_user.id, ),
    #                             id=job_name)
    # except Exception as ex:
    #     print(ex)

    scheduler.print_jobs()
    
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
        await bot.edit_message_text(text=_text,
                                    chat_id=callback.message.chat.id,
                                    message_id=msg[-1],
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
    callback_data = callback.data.split('__')[-1]

    _text = await save_data_to_storage(callback,
                                        state,
                                        session,
                                        bot,
                                        scheduler,
                                        callback_data)
    
    await callback.answer(text=_text,
                          show_alert=True)
    
    await redirect_to_(callback,
                       state,
                       session,
                       bot,
                       scheduler,
                       marker=action)
    
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
    callback_data = callback.data.split('_')[1:]
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
            await redirect_to_(callback,
                            state,
                            session,
                            bot,
                            scheduler,
                            marker=marker)
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
            await redirect_to_(callback,
                            state,
                            session,
                            bot,
                            scheduler,
                            marker=marker)
            

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
                    WbProduct.percent,
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
                product_id, link, actaul_price, start_price, user_id, time_create, name, percent, job_id = _product

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
                    OzonProductModel.percent,
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
                product_id, link, actaul_price, start_price, user_id, time_create, name, percent, job_id = _product


    time_create: datetime
    moscow_tz = pytz.timezone('Europe/Moscow')
    moscow_time = time_create.astimezone(moscow_tz)

    waiting_price = actaul_price - ((actaul_price * percent) / 100)

    _text = f'Привет {user_id}\nТвой {marker} <a href="{link}">товар</a>\n\nНачальная цена: {start_price}\nАктуальная цена: {actaul_price}\nВыставленный процент: {percent}\nОжидаемая(или ниже) цена товара:{waiting_price}\nДата начала отслеживания: {moscow_time}'

    # _kb = add_cancel_btn_to_photo_keyboard(photo_kb)

    _kb = create_remove_kb(user_id=callback.from_user.id,
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


@main_router.message()
async def any_input(message: types.Message,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot,
                    scheduler: AsyncIOScheduler):
    moscow_tz = pytz.timezone('Europe/Moscow')
    _now = datetime.now()
    moscow_time = _now.astimezone(moscow_tz)

    # _time_delta = moscow_time - timedelta(seconds=20)
    if message.from_user.id == int(DEV_ID):
        print(message.text, datetime.now())
    
    await check_user_last_message_time(message.from_user.id,
                                        moscow_time,
                                        message.text,
                                        state)
    # print(w)
    # await validate_link(message,
    #                     state,
    #                     session)
    await message.answer(text=message.text)