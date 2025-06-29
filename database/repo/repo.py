from sqlalchemy.ext.asyncio import async_sessionmaker


class Repo:
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker
