from datetime import datetime

from aiogram import types, Bot
from aiogram.fsm.context import FSMContext

from sqlalchemy import update, select, and_, or_, insert
from sqlalchemy.ext.asyncio import AsyncSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.base import User, WbProduct, WbPunkt, OzonProduct, UserJob

from utils.scheduler import push_check_wb_price


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
                    'basic_price': data.get('ozon_basic_price'),
                    'time_create': datetime.now(),
                    'user_id': callback.from_user.id,
                }
                
                query = (
                    insert(OzonProduct)\
                    .values(**_data)
                )

                await session.execute(query)

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
                            'basic_price': data.get('wb_basic_price'),
                            'actual_price': data.get('wb_product_price'),
                            'now_price': data.get('wb_product_price'),
                            'time_create': datetime.now(),
                            'user_id': callback.from_user.id,
                            'wb_punkt_id': _wb_punkt_id,
                            'push_price': float(data.get('push_price')),
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
    async with session as session:
        try:
            await session.execute(query)
            await session.commit()
        except Exception as ex:
            print(ex)
            await session.rollback()
        else:
            print('user added')
            return True


async def check_user(message: types.Message,
                     session: AsyncSession):
    async with session as session:
        query = (
            select(User)\
            .where(User.tg_id == message.from_user.id)
        )
        async with session as session:
            res = await session.execute(query)

            res = res.scalar_one_or_none()

        if res:
            return True
        else:
            return await add_user(message,
                                    session)


# async def try_add_file_ids_to_db(message: types.Message,
#                                  session: Session,
#                                  bot: Bot,
#                                  obj):
#     MassSendImage = Base.classes.general_models_masssendimage

#     # # images = select(MassSendMessage).options(joinedload(MassSendMessage.images))

#     for image in obj.general_models_masssendimage_collection:
#         # update_image_list = []
#         if image.file_id is None:
#             image_file = types.FSInputFile(path=f'/home/skxnny/web/backup_bestexchange/django_fastapi/media/{image.image}')
#             # upload image to telegram server
#             loaded_image = await message.answer_photo(image_file)
#             # delete image message from chat
#             # await message.delete()
#             await bot.delete_message(message.chat.id, loaded_image.message_id)

#             image_file_id = loaded_image.photo[0].file_id
#             print(image.id, image_file_id)
#             session.execute(update(MassSendImage).where(MassSendImage.id==image.id).values(file_id=image_file_id))
#     #         # image_dict = {
#     #         #     'id': image.id,
#     #         #     'file_id': image_file_id,
#     #         # }
#     #         # update_image_list.append(image_dict)
#     # # if update_image_list:
#     #     # session.execute(update(MassSendImage),
#     #     #                 update_image_list)
#     #     # session.bulk_update_mappings(
#     #     #     MassSendImage,
#     #     #     update_image_list,
#     #     # )
#     session.commit()

#     MassSendVideo = Base.classes.general_models_masssendvideo

#     for video in obj.general_models_masssendvideo_collection:
#         update_video_list = []
#         if video.file_id is None:
#             video_file = types.FSInputFile(path=f'/home/skxnny/web/backup_bestexchange/django_fastapi/media/{video.video}')
#             # upload image to telegram server
#             loaded_video = await message.answer_video(video_file,
#                                                       width=1920,
#                                                       height=1080)
#             print('*' * 10)
#             print(loaded_video)
#             print('*' * 10)
#             # delete image message from chat
#             await message.delete()
#             await bot.delete_message(message.chat.id, loaded_video.message_id)

#             video_file_id = loaded_video.video.file_id
#             session.execute(update(MassSendVideo).where(MassSendVideo.id==video.id).values(file_id=video_file_id))
#     #         print(video.id, video_file_id)
#     session.commit()
#     #         video_dict = {
#     #             'id': video.id,
#     #             'file_id': video_file_id,
#     #         }
#     #         update_video_list.append(video_dict)
#     # if update_video_list:
#     #     session.bulk_update_mappings(
#     #         MassSendVideo,
#     #         update_video_list,
#     #     )
#     #     # session.flush(obj.general_models_masssendimage_collection)
#     # session.commit()

#     MassSendFile = Base.classes.general_models_masssendfile
#     for file in obj.general_models_masssendfile_collection:
#         # update_image_list = []
#         if file.file_id is None:
#             file_file = types.FSInputFile(path=f'/home/skxnny/web/backup_bestexchange/django_fastapi/media/{file.file}')
#             # upload image to telegram server
#             loaded_file = await message.answer_document(file_file)
#             print('FILE')
#             print(loaded_file)
#             # delete image message from chat
#             # await message.delete()
#             await bot.delete_message(message.chat.id, loaded_file.message_id)

#             file_file_id = loaded_file.document.file_id
#             print(file.id, file_file_id)
#             session.execute(update(MassSendFile).where(MassSendFile.id==file.id).values(file_id=file_file_id))
#             session.commit()
#     # session.refresh(obj)
#     # images = [(image.id, image.file_id, types.InputMediaPhoto(media=types.FSInputFile(path=f'/home/skxnny/web/backup_bestexchange/django_fastapi/media/{image.image}'))) for image in m.general_models_masssendimage_collection]
#     # for image in images:
#     #     if image[1] is None:
#     #         # upload image to telegram server
#     #         loaded_image = await message.answer_photo(image[-1].media)
#     #         # delete image message from chat
#     #         await bot.delete_message(message.chat.id, message.message_id)
#     #         image_file_id = loaded_image.photo[0].file_id
#     #         print(image[0], image_file_id)
#     #         image_dict = {
#     #             'id': image[0],
#     #             'file_id': image_file_id,
#     #         }
#     #         update_image_list.append(image_dict)
#     #     else:
#     #         print('из БД', image[1])
#     # if update_image_list:
#     #     session.bulk_update_mappings(
#     #         MassSendImage,
#     #         update_image_list,
#     #     )
#     #     session.commit()
#     #     session.flush(obj.general_models_masssendimage_collection)


# async def try_add_file_ids(bot: Bot,
#                            session: Session,
#                            obj):
#     MassSendImage = Base.classes.general_models_masssendimage
#     for image in obj.general_models_masssendimage_collection:
#         if image.file_id is None:
#             # _path = f'/home/skxnny/web/backup_bestexchange/django_fastapi/media/{image.image}'
#             _path = f'https://api.moneyswap.online/media/{image.image}'

#             print(_path)
#             # image_file = types.FSInputFile(path=_path)
#             image_file = types.URLInputFile(url=_path)

#             # upload image to telegram server
#             loaded_image = await bot.send_photo(686339126, image_file)
#             print(loaded_image)
#             # delete image message from chat
#             await bot.delete_message(loaded_image.chat.id, loaded_image.message_id)

#             image_file_id = loaded_image.photo[0].file_id
#             print(image.id, image_file_id)
#             session.execute(update(MassSendImage).where(MassSendImage.id==image.id).values(file_id=image_file_id))

#     MassSendVideo = Base.classes.general_models_masssendvideo
#     for video in obj.general_models_masssendvideo_collection:
#         if video.file_id is None:
#             # _path = f'/home/skxnny/web/backup_bestexchange/django_fastapi/media/{video.video}'
#             _path = f'https://api.moneyswap.online/media/{video.video}'
#             print(_path)
#             video_file = types.URLInputFile(url=_path)
#             # upload video to telegram server
#             loaded_video = await bot.send_video(686339126,
#                                                 video_file,
#                                                 width=1920,
#                                                 height=1080)
#             # delete image message from chat
#             await bot.delete_message(loaded_video.chat.id, loaded_video.message_id)

#             video_file_id = loaded_video.video.file_id
#             session.execute(update(MassSendVideo).where(MassSendVideo.id==video.id).values(file_id=video_file_id))

#     MassSendFile = Base.classes.general_models_masssendfile
#     for file in obj.general_models_masssendfile_collection:
#         if file.file_id is None:
#             _path = f'https://api.moneyswap.online/media/{file.file}'

#             file_file = types.URLInputFile(url=_path)
#             # upload file to telegram server
#             loaded_file = await bot.send_document(686339126,
#                                                 file_file)
#             # delete image message from chat
#             await bot.delete_message(loaded_file.chat.id, loaded_file.message_id)

#             file_file_id = loaded_file.document.file_id
#             print(file.id, file_file_id)
#             session.execute(update(MassSendFile).where(MassSendFile.id==file.id).values(file_id=file_file_id))

#     session.commit()



# async def swift_sepa_data(state: FSMContext):
#     # res = []
#     data = await state.get_data()
#     request_text = 'Оплатить платеж' if data['request_type'] == 'pay' else 'Принять платеж'
#     # res.append(request_type)
#     request_type = f"Тип заявки: {request_text}"
#     country = f"Страна: {data['country']}"
#     amount = f"Сумма: {data['amount']}"
#     task_text = f"Комментарий: {data['task_text']}"
#     res = '\n'.join(
#         (request_type,
#          country,
#          amount,
#          task_text),
#         )
#     return res