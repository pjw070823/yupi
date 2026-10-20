import sqlite3
import unittest

from jungol import (JungolError, JungolStore, ProfileCache, Profile, account_path, format_joined,
                    parse_problem, parse_profile)

PAGE = (
    '<title>@pjw0823 - JUNGOL</title>'
    '<meta property="og:description" content="Silver IV · rank 3,202 · joined 5/1/2019"/>'
    '<dt class="jgacc-row-label">AC 레이팅</dt> <dd class="jgacc-row-value"><!--[!-->1,337점<!--]--></dd>'
)


class ParseTests(unittest.TestCase):
    def test_parse_profile(self):
        profile = parse_profile(PAGE, 56641)
        self.assertEqual((profile.account_id, profile.nickname, profile.rating, profile.tier),
                         (56641, 'pjw0823', 1337, 'Silver IV'))

    def test_parse_profile_extras(self):
        page = PAGE + '<div title="다음 티어까지 AC 레이팅 63 필요 · 이번 티어 구간 37% 진행">'
        profile = parse_profile(page, 1)
        self.assertEqual((profile.rank, profile.joined, profile.next_tier_points), (3202, '5/1/2019', 63))
        self.assertEqual(format_joined('5/1/2019'), '2019-05-01')

    def test_parse_problem(self):
        page = ('<meta property="og:title" content="두 정수 &amp; 더하기 · Bronze V"/>'
                '<meta property="og:description" content="Bronze V · 5,175 solved users · 13,726 submissions"/>')
        problem = parse_problem(page, 1000)
        self.assertEqual((problem.title, problem.tier, problem.solved_users, problem.submissions),
                         ('두 정수 & 더하기', 'Bronze V', 5175, 13726))
        self.assertEqual(problem.image_url, 'https://jungol.co.kr/og/problem/1000.png')

    def test_missing_rating(self):
        with self.assertRaises(JungolError):
            parse_profile('<title>@x - JUNGOL</title>', 1)

    def test_account_path(self):
        self.assertEqual(account_path(' 56641 '), '56641')
        self.assertEqual(account_path('pjw0823'), '@pjw0823')
        self.assertEqual(account_path('@pjw0823'), '@pjw0823')
        with self.assertRaises(JungolError):
            account_path('a/b')


class StoreTests(unittest.TestCase):
    def test_register_overwrites_per_guild(self):
        store = JungolStore(sqlite3.connect(':memory:'))
        store.init_db()
        store.register(1, 10, 100)
        store.register(1, 10, 200)
        store.register(2, 10, 300)
        self.assertEqual(store.members(1), [(10, 200)])
        self.assertEqual(store.members(2), [(10, 300)])
        self.assertEqual(store.account_id(1, 10), 200)
        self.assertIsNone(store.account_id(1, 11))

    def test_cache_expires(self):
        cache = ProfileCache(ttl=300)
        profile = Profile(1, 'a', 5, '')
        cache.put(profile, now=1000)
        self.assertIs(cache.get(1, now=1299), profile)
        self.assertIsNone(cache.get(1, now=1300))


if __name__ == '__main__':
    unittest.main()
