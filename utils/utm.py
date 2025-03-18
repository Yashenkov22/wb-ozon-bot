from sqlalchemy import insert

from db.base import get_session, UTM

from schemas import UTMSchema

async def add_utm_to_db(data: UTMSchema):
    print('1 ',data.__dict__)
    data = data.model_dump()
    print('2 ',data.__dict__)

    query = (
        insert(
            UTM
        )\
        .values(**data)
    )

    async for session in get_session():
        try:
            await session.execute(query)
            await session.commit()
        except Exception as ex:
            await session.rollback()
            print('ADD UTM ERROR', ex)
        else:
            print('UTM ADDED SUCCESSFULLY')
