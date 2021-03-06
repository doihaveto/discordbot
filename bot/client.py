import asyncio
import discord
import logging
from . import settings
from time import time
from collections import defaultdict

log = logging.getLogger(__name__)

class Client(discord.Client):
    def __init__(self, *args, **kwargs):
        self.custom_events = defaultdict(list)
        self.custom_commands = {}
        self.custom_commands_rates = {}
        super().__init__(*args, **kwargs)

    def dispatch(self, event, *args, **kwargs):
        super().dispatch(event, *args, **kwargs)
        method = 'on_' + event
        for coro in self.custom_events[method]:
            self._schedule_event(coro, method, *args, **kwargs)

    def register_event(self, event=None):
        def decorator(coro):
            if not asyncio.iscoroutinefunction(coro):
                raise TypeError('custom event registered must be a coroutine function')
            self.custom_events[event or coro.__name__].append(coro)
            log.debug('%s has successfully been registered as a custom event', event or coro.__name__)
            return coro
        return decorator

    def register_command(self, name=None, rate_limit=None, allow_private=False, allow_public=True, admin=False):
        ''' rate_limit = (3, 60) - allow 3 calls every 60 seconds '''
        def decorator(coro):
            if not asyncio.iscoroutinefunction(coro):
                raise TypeError('custom command registered must be a coroutine function')
            command = name or coro.__name__
            self.custom_commands[command] = {
                'coro': coro,
                'rate_limit': rate_limit,
                'allow_private': allow_private,
                'allow_public': allow_public,
                'admin': admin,
            }
            if rate_limit:
                self.custom_commands_rates[command] = []
            log.debug('%s has successfully been registered as a custom command', command)
            return coro
        return decorator

    def run(self):
        return super().run(settings.TOKEN)

client = Client(**settings.CLIENT_PARAMS)

@client.register_event()
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith(settings.COMMAND_PREFIX):
        parts = message.content.split(maxsplit=1)
        if len(parts) == 2:
            command_name, arg = parts
        else:
            command_name, arg = (parts[0], '')
        command_name = command_name[len(settings.COMMAND_PREFIX):]
        if command_name in client.custom_commands:
            command = client.custom_commands[command_name]
            if message.channel.type.name == 'private' and not command['allow_private']:
                return
            if message.channel.type.name != 'private' and not command['allow_public']:
                return
            if command['admin'] and message.author.id not in settings.ADMINS:
                return
            if command['rate_limit']:
                num_calls, seconds = command['rate_limit']
                client.custom_commands_rates[command_name] = [x for x in client.custom_commands_rates[command_name] if x > time() - seconds]
                if len(client.custom_commands_rates[command_name]) >= num_calls:
                    log.warning('Rate limit reached for command %s', command_name)
                    return
                client.custom_commands_rates[command_name].append(time())
            try:
                await command['coro'](message, arg)
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception(f'Ignoring exception in custom command {command_name}')
