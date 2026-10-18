import importlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from reminders import KST, ReminderStore, parse_reminder_time


class TimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 18, 12, 0, 45, tzinfo=KST)

    def test_relative_time(self):
        for text in ('+2d 1h 30m', ' +2d1h30m ', '+30m 1h 2d'):
            with self.subTest(text=text):
                self.assertEqual(parse_reminder_time(text, self.now),
                                 self.now + timedelta(days=2, hours=1, minutes=30))
        self.assertEqual(parse_reminder_time('+90m', self.now), self.now + timedelta(minutes=90))

    def test_absolute_time_is_kst(self):
        expected = datetime(2026, 10, 31, 20, 21, tzinfo=KST)
        self.assertEqual(parse_reminder_time('261031 20:21', self.now), expected)
        self.assertEqual(parse_reminder_time('261031 20:21', self.now.astimezone(timezone.utc)), expected)
        self.assertEqual(parse_reminder_time('991031 20:21', self.now).year, 2099)

    def test_leap_year_and_month_rollover(self):
        self.assertEqual(parse_reminder_time('280229 00:00', self.now).day, 29)
        now = datetime(2026, 12, 31, 23, 30, tzinfo=KST)
        self.assertEqual(parse_reminder_time('+1h', now), datetime(2027, 1, 1, 0, 30, tzinfo=KST))

    def test_invalid_and_past_times(self):
        for text in ('', '+', '+0m', '+-1h', '+1.5h', '+1h 2h', '+1h garbage',
                     '+1', '+1s', '261031', '261031 24:00', '261031 20:60',
                     '261332 20:21', '270229 00:00', '261018 12:00',
                     '251031 20:21', '261031 20:21 extra', '+' + '9' * 100 + 'd'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_reminder_time(text, self.now)


class StoreTests(unittest.TestCase):
    def test_restart_overdue_order_and_completed_reminders(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reminders.db'
            target = datetime(2026, 10, 31, 20, 21, tzinfo=KST)
            with sqlite3.connect(path) as connection:
                store = ReminderStore(connection)
                store.init_db()
                first = store.add(42, 123, '회의 준비', target)
                second = store.add(43, 123, "it's @everyone", target)
                self.assertEqual(store.due(target.timestamp() - 1), [])
            connection.close()
            with sqlite3.connect(path) as connection:
                store = ReminderStore(connection)
                store.init_db()
                due = store.due(target.timestamp() + 3600)
                self.assertEqual([row[0] for row in due], [first, second])
                self.assertEqual(due[0][1:], (42, 123, '회의 준비'))
                store.finish(first)
                store.finish(second, 'failed')
                self.assertEqual(store.due(target.timestamp() + 3600), [])
            connection.close()

    def test_retry_and_message_validation(self):
        with sqlite3.connect(':memory:') as connection:
            store = ReminderStore(connection)
            store.init_db()
            target = datetime(2026, 10, 31, 20, 21, tzinfo=KST)
            for text in ('a' * 1901,):
                with self.subTest(text=text[:10]), self.assertRaises(ValueError):
                    store.add(1, 2, text, target)
            reminder_id = store.add(1, 2, '알림', target)
            timestamp = target.timestamp()
            store.retry(reminder_id, timestamp)
            self.assertEqual(store.due(timestamp + 59), [])
            self.assertEqual(store.due(timestamp + 60)[0][0], reminder_id)
        connection.close()


class DiscordTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Load the real command tree without a token, network calls, or user DB.
        cls.connection = sqlite3.connect(':memory:')
        with patch('dotenv.load_dotenv'), patch('openrouter.OpenRouter'), \
             patch('sqlite3.connect', return_value=cls.connection), patch('discord.ext.commands.Bot.run'):
            cls.module = importlib.import_module('bot')

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.store = ReminderStore(self.connection)
        self.store.init_db()
        self.channel = SimpleNamespace(send=AsyncMock())
        self.bot = SimpleNamespace(wait_until_ready=AsyncMock(),
                                   get_channel=Mock(return_value=self.channel), fetch_channel=AsyncMock())
        self.patches = [patch.object(self.module, 'reminder_store', self.store),
                        patch.object(self.module, 'bot', self.bot),
                        patch.object(self.module, 'logger')]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.connection.close)

    def add_due(self):
        return self.store.add(42, 123, '@everyone <@99> 회의 준비',
                              datetime.now(KST) - timedelta(minutes=1))

    async def test_delivery_mentions_only_requester_and_is_not_repeated(self):
        self.add_due()
        await self.module.send_reminders.coro()
        await self.module.send_reminders.coro()
        self.channel.send.assert_awaited_once()
        args, kwargs = self.channel.send.call_args
        self.assertEqual(args[0], '<@42> [리마인드]\n**@everyone <@99> 회의 준비**')
        self.assertEqual(kwargs['allowed_mentions'].to_dict(),
                         {'users': [42], 'parse': []})
        self.assertEqual(self.store.due(datetime.now(KST).timestamp()), [])

    async def test_missing_cache_fetches_channel(self):
        self.add_due()
        self.bot.get_channel.return_value = None
        self.bot.fetch_channel.return_value = self.channel
        await self.module.send_reminders.coro()
        self.bot.fetch_channel.assert_awaited_once_with(123)
        self.channel.send.assert_awaited_once()

    async def test_transient_failure_retries_and_other_reminders_still_send(self):
        failed_id = self.add_due()
        self.add_due()
        self.channel.send.side_effect = [OSError('offline'), None]
        await self.module.send_reminders.coro()
        self.assertEqual(self.channel.send.await_count, 2)
        now = datetime.now(KST).timestamp()
        self.assertEqual(self.store.due(now), [])
        self.assertEqual([row[0] for row in self.store.due(now + 61)], [failed_id])

    async def test_deleted_channel_or_missing_permission_marks_failed(self):
        for error_type, status in ((self.module.NotFound, 404), (self.module.Forbidden, 403)):
            with self.subTest(status=status):
                reminder_id = self.add_due()
                self.channel.send.side_effect = error_type(SimpleNamespace(status=status, reason='unavailable'), 'error')
                await self.module.send_reminders.coro()
                self.assertEqual(self.connection.execute('SELECT status FROM reminders WHERE id = ?',
                                                        (reminder_id,)).fetchone()[0], 'failed')

    async def test_command_registration_and_persistence(self):
        command = self.module.remind
        self.assertEqual([p.name for p in command.parameters], ['시간', '메시지'])
        self.assertEqual([p.required for p in command.parameters], [True, False])
        interaction = SimpleNamespace(user=SimpleNamespace(id=42), channel_id=123,
                                      response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
                                      followup=SimpleNamespace(send=AsyncMock()))
        await command.callback(interaction, '+2d 1h 30m', '회의 준비')
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        self.assertEqual(self.connection.execute('SELECT user_id, channel_id, message FROM reminders').fetchone(),
                         (42, 123, '회의 준비'))

    async def test_command_rejects_invalid_input_without_saving(self):
        for time_text, message in (('invalid', '알림'), ('+1m', 'a' * 1901)):
            interaction = SimpleNamespace(user=SimpleNamespace(id=42), channel_id=123,
                                          response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
                                          followup=SimpleNamespace(send=AsyncMock()))
            await self.module.remind.callback(interaction, time_text, message)
            interaction.response.send_message.assert_awaited_once()
            interaction.response.defer.assert_not_awaited()
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM reminders').fetchone()[0], 0)

    async def test_optional_message_is_saved_and_delivered_without_empty_line(self):
        for supplied_message in (None, '   '):
            interaction = SimpleNamespace(user=SimpleNamespace(id=42), channel_id=123,
                                          response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
                                          followup=SimpleNamespace(send=AsyncMock()))
            if supplied_message is None:
                await self.module.remind.callback(interaction, '+1m')
            else:
                await self.module.remind.callback(interaction, '+1m', supplied_message)
            interaction.followup.send.assert_awaited_once()
        self.assertEqual(self.connection.execute('SELECT message FROM reminders').fetchall(), [('',), ('',)])
        self.connection.execute('UPDATE reminders SET next_attempt_at = 0')
        self.connection.commit()
        await self.module.send_reminders.coro()
        self.assertEqual(self.channel.send.await_count, 2)
        for call in self.channel.send.call_args_list:
            self.assertEqual(call.args[0], '<@42> [리마인드]')

    async def test_save_failure_does_not_confirm_reservation(self):
        interaction = SimpleNamespace(user=SimpleNamespace(id=42), channel_id=123,
                                      response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
                                      followup=SimpleNamespace(send=AsyncMock()))
        with patch.object(self.store, 'add', side_effect=sqlite3.OperationalError('locked')):
            await self.module.remind.callback(interaction, '+1m', '알림')
        self.assertIn('저장하지 못했어요', interaction.followup.send.call_args.args[0])

    async def test_reconnect_does_not_start_duplicate_worker(self):
        self.bot.user = SimpleNamespace(id=1)
        self.bot.tree = SimpleNamespace(sync=AsyncMock(return_value=[]))
        worker = Mock()
        worker.is_running.return_value = False
        with patch.object(self.module, 'init_db'), patch.object(self.module, 'send_reminders', worker):
            await self.module.on_ready()
            worker.is_running.return_value = True
            await self.module.on_ready()
        worker.start.assert_called_once()


if __name__ == '__main__':
    unittest.main()
