from math import ceil

import pytz

from datetime import datetime

from aiogram import Router, types, Bot, F
from aiogram.filters import Command, or_f, and_f
from aiogram.fsm.context import FSMContext

from sqlalchemy import and_, insert, select, update, or_, delete, func, Integer, Float
from sqlalchemy.sql.expression import cast

from sqlalchemy.ext.asyncio import AsyncSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from keyboards import (create_or_add_exit_btn,
                       create_or_add_return_to_product_list_btn,
                       create_pagination_page_kb,
                       create_or_add_cancel_btn,
                       create_remove_and_edit_sale_kb,
                       create_reply_start_kb)

from states import AnyProductStates, EditSale

from utils.handlers import (DEFAULT_PAGE_ELEMENT_COUNT,
                            check_input_link,
                            delete_prev_subactive_msg,
                            generate_pretty_amount,
                            check_user,
                            show_product_list,
                            try_delete_prev_list_msgs)
from utils.scheduler import add_product_task

from db.base import OzonProduct as OzonProductModel, User, Base, UserJob, WbProduct


main_router = Router()

moscow_tz = pytz.timezone('Europe/Moscow')

start_text = '🖐Здравствуйте, {}\n\nС помощью этого бота вы сможете отследить изменение цены на понравившиеся товары в маркетплейсах Wildberries и Ozon.'


@main_router.message(Command('start'))
async def start(message: types.Message | types.CallbackQuery,
                state: FSMContext,
                session: AsyncSession,
                bot: Bot,
                scheduler: AsyncIOScheduler):
    _message = message

    await try_delete_prev_list_msgs(message.chat.id,
                                    state)
    
    await state.clear()
    
    await check_user(message,
                     session)
        
    await state.update_data(action=None)

    if isinstance(message, types.CallbackQuery):
        message = message.message

    _kb = create_reply_start_kb()
    await bot.send_message(text=start_text.format(message.from_user.username),
                                chat_id=_message.from_user.id,
                                reply_markup=_kb.as_markup(resize_keyboard=True))
    
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
    
    # data = await state.get_data()

    _text = 'Отправьте ссылку на товар'

    _kb = create_or_add_exit_btn()

    add_msg = await bot.send_message(text=_text,
                           chat_id=message.from_user.id,
                           reply_markup=_kb.as_markup())
    
    await state.update_data(add_msg=(add_msg.chat.id, add_msg.message_id))

    try:
        await message.delete()
    except Exception:
        pass


@main_router.message(and_f(AnyProductStates.link, F.content_type == types.ContentType.TEXT))
async def any_product_proccess(message: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    data = await state.get_data()
    add_msg: tuple = data.get('add_msg')

    if message.text == 'Посмотреть товары':
        try:
            await bot.delete_message(chat_id=add_msg[0],
                                     message_id=add_msg[-1])
        except Exception as ex:
            print(ex)

        await state.set_state()
        await get_all_products_by_user(message,
                                       state,
                                       session,
                                       bot,
                                       scheduler)
        return

    # _add_msg: tuple = data.get('_add_msg')

    # if _add_msg:
    #     try:
    #         await bot.delete_message(chat_id=_add_msg[0],
    #                                  message_id=_add_msg[-1])
    #     except Exception as ex:
    #         print(ex)

    # add_msg: tuple = data.get('add_msg')
    # await delete_prev_subactive_msg(data)

    print('add msg', add_msg)

    _message_text = message.text.strip().split()

    _name = link = None

    if len(_message_text) > 1:
        *_name, link = _message_text
        _name = ' '.join(_name)
    else:
        link = message.text.strip()

    check_link = check_input_link(link) # None or Literal['WB', 'OZON']

    if check_link:
        await delete_prev_subactive_msg(data)
        sub_active_msg: types.Message = await message.answer(text=f'{check_link} товар добавляется...')

        user_data = {
            'msg': (message.chat.id, message.message_id),
            'name': _name,
            'link': link,
            '_add_msg_id': sub_active_msg.message_id,
            'product_marker': check_link,
        }

        scheduler.add_job(add_product_task, DateTrigger(run_date=datetime.now()), (user_data, ))
    else:
        await delete_prev_subactive_msg(data)
        sub_active_msg: types.Message = await message.answer(text='Невалидная ссылка')

    await state.update_data(_add_msg=(sub_active_msg.chat.id, sub_active_msg.message_id))
    
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
    await try_delete_prev_list_msgs(message.chat.id,
                                    state)
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
               cast(WbProduct.actual_price, Integer).label('actual_price'),
               cast(WbProduct.start_price, Integer).label('start_price'),
               WbProduct.user_id,
               cast(func.extract('epoch', WbProduct.time_create), Float).label('time_create'),
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
            cast(OzonProductModel.actual_price, Integer).label('actual_price'),
            cast(OzonProductModel.start_price, Integer).label('start_price'),
            OzonProductModel.user_id,
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
        await delete_prev_subactive_msg(data)
        sub_active_msg = await message.answer('Нет добавленных продуктов')
        await state.update_data(_add_msg=(sub_active_msg.chat.id, sub_active_msg.message_id))
        return
    
    len_product_list = len(product_list)
    
    product_list = sorted(list(map(lambda el: tuple(el), product_list)),
                          key=lambda el: el[5],   # sort by time_create field
                          reverse=True)           # order by desc
    try:
        wb_product_count = sum(1 for product in product_list if product[6] == 'wb')
        ozon_product_count = len_product_list - wb_product_count
    except Exception as ex:
        print('sum eror', ex)
        wb_product_count = 0
        ozon_product_count = len_product_list

    pages = ceil(len_product_list / DEFAULT_PAGE_ELEMENT_COUNT)
    current_page = 1

    view_product_dict = {
        'len_product_list': len_product_list,
        'pages': pages,
        'current_page': current_page,
        'product_list': product_list,
        'ozon_product_count': ozon_product_count,
        'wb_product_count': wb_product_count,
    }

    await show_product_list(view_product_dict,
                            message.from_user.id,
                            state)
    try:
        await message.delete()
    except Exception:
        pass


@main_router.callback_query(F.data == 'pagination_page')
async def pagination_page(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler):
    data = await state.get_data()

    product_dict: dict = data.get('view_product_dict')

    list_msg: tuple = product_dict.get('list_msg')

    _kb = create_pagination_page_kb(product_dict)
    _kb = create_or_add_return_to_product_list_btn(_kb)

    await bot.edit_message_text(chat_id=list_msg[0],
                                message_id=list_msg[-1],
                                text='Выберите страницу, на которую хотите перейти',
                                reply_markup=_kb.as_markup())
    await callback.answer()


@main_router.callback_query(F.data.startswith('go_to_page'))
async def go_to_selected_page(callback: types.Message | types.CallbackQuery,
                              state: FSMContext,
                              session: AsyncSession,
                              bot: Bot,
                              scheduler: AsyncIOScheduler):
    data = await state.get_data()

    selected_page = callback.data.split('_')[-1]
    
    product_dict: dict = data.get('view_product_dict')

    product_dict['current_page'] = int(selected_page)

    await show_product_list(product_dict,
                            callback.from_user.id,
                            state)
    await callback.answer()


@main_router.callback_query(F.data.startswith('page'))
async def switch_page(callback: types.Message | types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler):
    callback_data = callback.data.split('_')[-1]
    
    data = await state.get_data()
    
    product_dict = data.get('view_product_dict')

    if not product_dict:
        await callback.answer(text='Ошибка',
                              show_alert=True)
        return
    
    if callback_data == 'next':
        product_dict['current_page'] += 1
    else:
        product_dict['current_page'] -= 1

    await show_product_list(product_dict,
                            callback.from_user.id,
                            state)
    await callback.answer()
    

@main_router.callback_query(F.data == 'cancel')
async def callback_cancel(callback: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    await state.set_state()
    try:
        await callback.message.delete()
    except Exception:
        pass
    finally:
        await callback.answer()

    
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
    finally:
        await callback.answer()
        

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
    finally:
        await callback.answer()


@main_router.callback_query(F.data == 'return_to_product_list')
async def back_to_product_list(callback: types.Message | types.CallbackQuery,
                               state: FSMContext):
    data = await state.get_data()

    product_dict: dict = data.get('view_product_dict')
    
    if product_dict:
            await show_product_list(product_dict=product_dict,
                                    user_id=callback.from_user.id,
                                    state=state)
            await callback.answer()
    else:
        await callback.answer(text='Что то пошло не так',
                              show_alert=True)


@main_router.callback_query(F.data.startswith('delete'))
async def delete_callback(callback: types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler):
    with_redirect = True

    data = await state.get_data()
    
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
                        WbProduct.id == int(product_id),
                    )
                )
            )
            async with session.begin():
                await session.execute(query1)
                await session.execute(query2)
                try:
                    await session.commit()
                    
                    scheduler.remove_job(job_id=job_id,
                                         jobstore='sqlalchemy')
                except Exception as ex:
                    print(ex)
                    await session.rollback()
                else:
                    await callback.answer('Товар успешно удален',
                                          show_alert=True)
            
            if with_redirect:
                product_dict: dict = data.get('view_product_dict')

                pages: int = product_dict.get('pages')
                current_page: int = product_dict.get('current_page')
                product_list: list = product_dict.get('product_list')
                ozon_product_count: int = product_dict.get('ozon_product_count')
                wb_product_count: int = product_dict.get('wb_product_count')
                list_msg: tuple = product_dict.get('list_msg')

                for idx, product in enumerate(product_list):
                    print(product)
                    print(product[0], product_id)
                    print(product[6], marker)
                    if product[0] == int(product_id) and product[6] == marker:
                        del product_list[idx]
                
                wb_product_count -= 1
                
                len_product_list = len(product_list)

                pages = ceil(len_product_list / DEFAULT_PAGE_ELEMENT_COUNT)

                if current_page > pages:
                    current_page -= 1

                len_product_list = len(product_list)

                view_product_dict = {
                    'len_product_list': len_product_list,
                    'pages': pages,
                    'current_page': current_page,
                    'product_list': product_list,
                    'ozon_product_count': ozon_product_count,
                    'wb_product_count': wb_product_count,
                    'list_msg': list_msg,
                }

                await state.update_data(view_product_dict=view_product_dict)

                await back_to_product_list(callback,
                                           state)
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
                        OzonProductModel.id == int(product_id),
                    )
                )
            )
            async with session.begin():
                await session.execute(query1)
                await session.execute(query2)
                try:
                    await session.commit()

                    scheduler.remove_job(job_id=job_id,
                                         jobstore='sqlalchemy')
                except Exception as ex:
                    print(ex)
                    await session.rollback()
                else:
                    await callback.answer('Товар успешно удален',
                                          show_alert=True)
            
            if with_redirect:
                product_dict: dict = data.get('view_product_dict')

                pages: int = product_dict.get('pages')
                current_page: int = product_dict.get('current_page')
                product_list: list = product_dict.get('product_list')
                ozon_product_count: int = product_dict.get('ozon_product_count')
                wb_product_count: int = product_dict.get('wb_product_count')
                list_msg: tuple = product_dict.get('list_msg')

                for idx, product in enumerate(product_list):
                    if product[0] == int(product_id) and product[6] == marker:
                        del product_list[idx]

                ozon_product_count -= 1
                
                len_product_list = len(product_list)

                pages = ceil(len_product_list / DEFAULT_PAGE_ELEMENT_COUNT)

                if current_page > pages:
                    current_page -= 1

                len_product_list = len(product_list)

                view_product_dict = {
                    'len_product_list': len_product_list,
                    'pages': pages,
                    'current_page': current_page,
                    'product_list': product_list,
                    'ozon_product_count': ozon_product_count,
                    'wb_product_count': wb_product_count,
                    'list_msg': list_msg,
                }

                await state.update_data(view_product_dict=view_product_dict)
                await back_to_product_list(callback,
                                           state)
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
    
    callback_data = callback.data.split('_')
    callback_prefix = callback_data[0]

    marker, user_id, product_id = callback_data[1:]

    with_redirect = True

    if callback_prefix.endswith('rd'):
        with_redirect = False

    if with_redirect:
        _sale_data: dict = data.get('sale_data')

        link = _sale_data.get('link')
        sale = _sale_data.get('sale')
        start_price = _sale_data.get('start_price')
    else:
        product_model = WbProduct if marker == 'wb' else OzonProductModel
        query = (
            select(
                product_model.link,
                product_model.sale,
                product_model.start_price,
            )\
            .where(
                and_(
                    product_model.id == int(product_id),
                    product_model.user_id == callback.from_user.id,
                    )
                )
        )
        async with session as _session:
            res = await _session.execute(query)
        
        _sale_data = res.fetchall()

        link, sale, start_price = _sale_data[0]

    await state.update_data(
        sale_data={
            'user_id': user_id,
            'product_id': product_id,
            'marker': marker,
            'link': link,
            'sale': sale,
            'start_price': start_price,
            'with_redirect': with_redirect,
        }
        )
    await state.set_state(EditSale.new_sale)

    _kb = create_or_add_cancel_btn()

    msg = await bot.edit_message_text(text=f'<b>Установленная скидка на Ваш {marker.upper()} <a href="{link}">товар</a> {sale}</b>\n\nУкажите новую скидку <b>как число</b> в следующем сообщении',
                                chat_id=callback.from_user.id,
                                message_id=callback.message.message_id,
                                reply_markup=_kb.as_markup())
    
    await state.update_data(msg=(msg.chat.id, msg.message_id))
    await callback.answer()


@main_router.message(and_f(EditSale.new_sale), F.content_type == types.ContentType.TEXT)
async def edit_sale_proccess(message: types.Message | types.CallbackQuery,
                            state: FSMContext,
                            session: AsyncSession,
                            bot: Bot,
                            scheduler: AsyncIOScheduler):
    data = await state.get_data()

    new_sale = message.text.strip()

    await delete_prev_subactive_msg(data)

    if not new_sale.isdigit():
        sub_active_msg = await message.answer(text=f'Невалидные данные\nОжидается число, передано: {new_sale}')
        await state.update_data(_add_msg=(sub_active_msg.chat.id, sub_active_msg.message_id))
    
        try:
            await message.delete()
        except Exception:
            pass

        return

    product_dict: dict = data.get('view_product_dict')

    msg: tuple = product_dict.get('msg')

    sale_data: dict = data.get('sale_data')

    if not sale_data:
        sub_active_msg = await message.answer('Ошибка')
        await state.update_data(_add_msg=(sub_active_msg.chat.id, sub_active_msg.message_id))

        try:
            await message.delete()
        except Exception:
            pass

        return
    
    user_id = sale_data.get('user_id')
    product_id = sale_data.get('product_id')
    marker = sale_data.get('marker')
    start_price = sale_data.get('start_price')
    with_redirect = sale_data.get('with_redirect')

    if start_price <= float(new_sale):
        sub_active_msg = await message.answer(text=f'Невалидные данные\nСкидка не может быть больше или равной цене товара\nПередано {new_sale}, Начальная цена товара: {start_price}')
        await state.update_data(_add_msg=(sub_active_msg.chat.id, sub_active_msg.message_id))

        try:
            await message.delete()
        except Exception:
            pass

        return

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
            sub_active_msg = await message.answer('Не удалось обновить скидку')
        else:
            sub_active_msg = await message.answer('Скидка обновлена')

            await state.update_data(sale_data=None,
                                    _add_msg=(sub_active_msg.chat.id, sub_active_msg.message_id))
            await state.set_state()

            if with_redirect:
                await show_product_list(product_dict=product_dict,
                                        user_id=message.from_user.id,
                                        state=state)
            else:
                try:
                    await bot.delete_message(chat_id=msg[0],
                                             message_id=msg[-1])
                except Exception as ex:
                    print(ex)
            
    try:
        await message.delete()
    except Exception:
        pass
            

@main_router.callback_query(F.data.startswith('view-product1'))
async def view_product(callback: types.CallbackQuery,
                        state: FSMContext,
                        session: AsyncSession,
                        bot: Bot,
                        scheduler: AsyncIOScheduler,
                        marker: str = None):
    data = await state.get_data()

    product_dict: dict = data.get('view_product_dict')

    list_msg: tuple = product_dict.get('list_msg')

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
    
    waiting_price = start_price - sale

    _text_start_price = generate_pretty_amount(start_price)
    _text_product_price = generate_pretty_amount(actaul_price)

    _text_sale = generate_pretty_amount(sale)
    _text_price_with_sale = generate_pretty_amount((start_price - sale))
    
    _text = f'Название: <a href="{link}">{name}</a>\nМаркетплейс: {product_marker}\n\nНачальная цена: {_text_start_price}\nАктуальная цена: {_text_product_price}\n\nОтслеживается изменение цены на: {_text_sale}\nОжидаемая цена: {_text_price_with_sale}'

    await state.update_data(
        sale_data={
            'link': link,
            'sale': sale,
            'start_price': start_price,
        }
    )

    _kb = create_remove_and_edit_sale_kb(user_id=callback.from_user.id,
                                         product_id=product_id,
                                         marker=marker,
                                         job_id=job_id,
                                         with_redirect=True)
    _kb = create_or_add_return_to_product_list_btn(_kb)

    if list_msg:
        await bot.edit_message_text(chat_id=list_msg[0],
                                    message_id=list_msg[-1],
                                    text=_text,
                                    reply_markup=_kb.as_markup())
    else:
        list_msg: types.Message =  bot.send_message(chat_id=callback.from_user.id,
                                                    text=_text,
                                                    reply_markup=_kb.as_markup())
        await state.update_data(list_msg=(list_msg.chat.id, list_msg.message_id))
        
    await callback.answer()            


@main_router.message(F.content_type == types.ContentType.TEXT)
async def any_input(message: types.Message,
                    state: FSMContext,
                    session: AsyncSession,
                    bot: Bot,
                    scheduler: AsyncIOScheduler):  
    data = await state.get_data()

    await delete_prev_subactive_msg(data)

    # _add_msg: tuple = data.get('_add_msg')

    # if _add_msg:
    #     try:
    #         await bot.delete_message(chat_id=_add_msg[0],
    #                                  message_id=_add_msg[-1])
    #     except Exception as ex:
    #         print(ex)

    _message_text = message.text.strip().split()

    _name = link = None

    if len(_message_text) > 1:
        *_name, link = _message_text
        _name = ' '.join(_name)
    else:
        link = message.text.strip()

    check_link = check_input_link(link)

    if check_link:

        sub_active_msg = await message.answer(text=f'{check_link} товар добавляется...')

        user_data = {
            'msg': (message.chat.id, message.message_id),
            'name': _name,
            'link': link,
            '_add_msg_id': sub_active_msg.message_id,
            'product_marker': check_link,
        }


        scheduler.add_job(add_product_task, DateTrigger(run_date=datetime.now()), (user_data, ))
    else:
        sub_active_msg = await message.answer(text='Невалидная ссылка')
    
    await state.update_data(_add_msg=(sub_active_msg.chat.id, sub_active_msg.message_id))
    
    try:
        await message.delete()
    except Exception as ex:
        print(ex)