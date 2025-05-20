from background.tasks import new_push_check_ozon_price, new_push_check_wb_price
from background.base import redis_settings

from config import REDIS_HOST, REDIS_PASSWORD


async def startup(ctx):
    print("Worker is starting up...")

async def shutdown(ctx):
    print("Worker is shutting down...")

class WorkerSettings:
    functions = [
        new_push_check_ozon_price,
        new_push_check_wb_price,
    ]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "arq:low"
    redis_settings = redis_settings

