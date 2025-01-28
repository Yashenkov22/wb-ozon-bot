from typing import Literal
from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def create_start_kb():
    _kb = InlineKeyboardBuilder()
    _kb.add(types.InlineKeyboardButton(text='WB бот',
                                       callback_data='bot_wb'))
    _kb.row(types.InlineKeyboardButton(text='OZON бот',
                                       callback_data='bot_ozon'))
    # _kb.row(types.InlineKeyboardButton(text='Посмотреть цену товара',
    #                                    callback_data='check_price'))

    return _kb


def create_wb_start_kb():
    _kb = InlineKeyboardBuilder()
    _kb.add(types.InlineKeyboardButton(text='Добавить пункт выдачи',
                                       callback_data='add_punkt'))
    _kb.row(types.InlineKeyboardButton(text='Посмотреть свои пункты выдачи',
                                       callback_data='list_punkt'))
    _kb.row(types.InlineKeyboardButton(text='Посмотреть цену товара',
                                       callback_data='check_price'))

    return _kb


def create_bot_start_kb(marker: Literal['wb', 'ozon']):
    _kb = InlineKeyboardBuilder()
    
    if marker == 'wb':
        _kb.add(types.InlineKeyboardButton(text='Добавить пункт выдачи',
                                        callback_data='add_punkt'))
        _kb.row(types.InlineKeyboardButton(text='Посмотреть свои пункты выдачи',
                                        callback_data='list_punkt'))
        _kb.row(types.InlineKeyboardButton(text='Добавить товар',
                                        callback_data='add_wb_product'))
        _kb.row(types.InlineKeyboardButton(text='Посмотреть товары',
                                        callback_data='view_price'))

    else:
        _kb.add(types.InlineKeyboardButton(text='Добавить товар',
                                           callback_data='add_product'))
        _kb.add(types.InlineKeyboardButton(text='Посмотреть товар',
                                           callback_data='list_product'))
        _kb.add(types.InlineKeyboardButton(text='Удалить все товары',
                                           callback_data='remove_all_products')) 

    return _kb


def create_or_add_cancel_btn(_kb: InlineKeyboardBuilder = None):
    if _kb is None:
        _kb = InlineKeyboardBuilder()

    _kb.row(types.InlineKeyboardButton(text='Отменить',
                                       callback_data='cancel'))
    
    return _kb


def add_back_btn(_kb: InlineKeyboardBuilder):
    _kb.row(types.InlineKeyboardButton(text='На главную',
                                       callback_data=f'to_main'))
    
    return _kb


def create_done_kb(marker: Literal['wb_punkt',
                                   'wb_product',
                                   'ozon_product']):
    _kb = InlineKeyboardBuilder()

    _kb.add(types.InlineKeyboardButton(text='Отправить',
                                       callback_data=f'done__{marker}'))
    
    return _kb



def create_remove_kb(user_id: int,
                     product_id: str,
                     marker: Literal['wb', 'ozon'],
                     job_id: str,
                     _kb: InlineKeyboardBuilder = None,
                     with_redirect: bool = True):
    if not _kb:
        _kb = InlineKeyboardBuilder()

    _callback_data = f'{marker}_{user_id}_{product_id}_{job_id}'

    if with_redirect:
        _callback_data = f'delete_{_callback_data}'
        # _text = 'Удалить товар'
    else:
        _callback_data = f'delete.no.rd_{_callback_data}'
    
    _text = 'Перестать отслеживать'

    _kb.row(types.InlineKeyboardButton(text=_text,
                                       callback_data=_callback_data))
    
    return _kb


def create_remove_and_edit_sale_kb(user_id: int,
                                   product_id: str,
                                   marker: Literal['wb', 'ozon'],
                                   job_id: str,
                                   link: str,
                                   sale: float,
                                   _kb: InlineKeyboardBuilder = None,
                                   with_redirect: bool = True):
    if not _kb:
        _kb = InlineKeyboardBuilder()

    _callback_data = f'{marker}_{user_id}_{product_id}'

    if link.find('?') > 0:
        print('yes')
        link = link[:link.find('?')]

    if with_redirect:
        delete_callback_data = f'delete_{_callback_data}_{job_id}'
        edit_sale_callback_data = f'edit.sale_{_callback_data}_{link}_{sale}'
        # _text = 'Удалить товар'
    else:
        # _callback_data = f'delete.no.rd_{_callback_data}'
        delete_callback_data = f'delete.no.rd{_callback_data}_{job_id}'
        edit_sale_callback_data = f'edit.sale.no.rd_{_callback_data}_{link}_{sale}'
    
    # _text = 'Перестать отслеживать'

    _kb.row(types.InlineKeyboardButton(text='Изменить сумму скидки',
                                       callback_data=edit_sale_callback_data))
    _kb.row(types.InlineKeyboardButton(text='Перестать отслеживать',
                                       callback_data=delete_callback_data))
    
    return _kb



def create_photo_keyboard(kb_init: str):
    product_kb = InlineKeyboardBuilder()
    match kb_init:
        case 'start':
            product_kb.add(types.InlineKeyboardButton(text='Следующая',
                                                    callback_data='product_next'))
        case 'mid':
            product_kb.add(types.InlineKeyboardButton(text='Предыдущая',
                                                    callback_data='product_prev'))
            product_kb.add(types.InlineKeyboardButton(text='Следующая',
                                                    callback_data='product_next'))
        case 'end':
            product_kb.add(types.InlineKeyboardButton(text='Предыдущая',
                                                    callback_data='product_prev'))

    # product_kb.row(types.InlineKeyboardButton(text='Назад',
    #                                         callback_data='cancel'))
    return product_kb


def add_cancel_btn_to_photo_keyboard(_kb: InlineKeyboardBuilder):
    _kb.row(types.InlineKeyboardButton(text='Назад',
                                        callback_data='cancel'))
    return _kb



def create_product_list_kb(user_id: int,
                           product_list: list,
                           marker: Literal['wb', 'ozon']):
    _kb = InlineKeyboardBuilder()

    for product in product_list:
        product_id, link, actaul_price, start_price, user_id, time_create, name, sale, job_id = product
        _callback_data = f'view-product_{user_id}_{marker}_{product_id}'

        _kb.row(types.InlineKeyboardButton(text=name,
                                           callback_data=_callback_data))
    
    return _kb



def add_or_create_close_kb(_kb: InlineKeyboardBuilder = None):
    if not _kb:
        _kb = InlineKeyboardBuilder()

    _kb.add(types.InlineKeyboardButton(text='Закрыть',
                                       callback_data='close'))
    
    return _kb