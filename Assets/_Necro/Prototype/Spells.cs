using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 주인공의 기술. 칸 수는 그대로 두고 단계(하급 → 상급 → 금주)에 따라 같은 자리의 기술이 바뀐다.
    // 프로토타입에서는 묘지기를 쓰러뜨리면 상급, 고룡을 쓰러뜨리면 금주가 한꺼번에 열린다.
    public static class Spells
    {
        public static readonly string[] TierName = { "하급", "상급", "금주" };
        public static readonly string[] BasicName = { "영혼 화살", "영혼 탄막", "영혼 폭풍" };
        public static readonly string[] SpearName = { "뼈 창", "뼈 창 비", "거신의 척추" };
        public static readonly string[] BlastName = { "시체 폭발", "연쇄 폭발", "망자의 해일" };
        public static readonly string[] BuffName = { "군단 강화", "광란", "불사의 군단" };
        public static readonly string[] RaiseName = { "시체 지배", "대량 지배", "왕관의 부름" };

        public static readonly float[] SpearCd = { 4f, 6f, 9f }, SpearMana = { 15f, 22f, 30f };
        public static readonly float[] BlastCd = { 6f, 7f, 14f }, BlastMana = { 20f, 24f, 35f };
        public static readonly float[] BuffCd = { 14f, 18f, 30f }, BuffMana = { 25f, 30f, 40f };
        public static readonly float[] RaiseRange = { 12f, 24f, 60f };
        public const float LegionCd = 90f, LegionMana = 50f, LegionTime = 30f;
        public const float DescentCd = 45f, DescentMana = 40f;

        const int AimMask = ~(1 << 2);
        static readonly Color Soul = new Color(0.72f, 0.45f, 1f);
        static readonly Color Bone = new Color(0.95f, 0.92f, 0.8f);
        static readonly Color Rot = new Color(0.6f, 1f, 0.35f);
        static readonly Color Tide = new Color(0.45f, 1f, 0.75f);
        static readonly List<Unit> buf = new List<Unit>();
        static readonly List<Corpse> corpses = new List<Corpse>();

        // 겨누는 지점: 겨눈 적 → 화면 가운데가 닿는 땅 → 앞쪽 땅
        public static Vector3 AimGround(PlayerCtl p, Transform cam, float maxDist)
        {
            if (p.focus != null) return p.focus.transform.position;
            RaycastHit hit;
            if (Physics.Raycast(cam.position, cam.forward, out hit, maxDist, AimMask, QueryTriggerInteraction.Ignore)) return hit.point;
            Vector3 q = p.transform.position + Util.Flat(cam.forward).normalized * 18f;
            q.y = World.GroundY(q);
            return q;
        }

        static Vector3 OnGround(Vector3 p)
        {
            p.y = World.GroundY(new Vector3(p.x, p.y + 1f, p.z));
            return p;
        }

        // ───────────── 기본 공격 (다음 발사까지의 간격을 돌려준다) ─────────────
        public static float Basic(PlayerCtl p, Transform cam)
        {
            float dmg = 15f + 2f * p.level;
            Vector3 tip = p.rig.staffTip.position;
            if (p.tier == 0)
            {
                // 영혼 화살: 한 발씩
                if (p.focus != null) Projectile.Fire(p, p.focus, tip, dmg, Soul, 32f);
                else Projectile.FireAt(p, Team.Enemy, tip, cam.position + cam.forward * 40f, 0f, Soul, 32f, 0f, 0.3f);
                return 0.38f;
            }
            if (p.tier == 1)
            {
                // 영혼 탄막: 겨눈 적과 그 주변의 적 셋까지 따라가는 다발
                if (p.focus == null)
                {
                    Projectile.FireAt(p, Team.Enemy, tip, cam.position + cam.forward * 40f, 0f, Soul, 34f, 0f, 0.26f);
                    return 0.42f;
                }
                Projectile.Fire(p, p.focus, tip, dmg * 0.8f, Soul, 34f, 0f, 0.28f);
                Vector3 fp = p.focus.transform.position;
                int extra = 0;
                foreach (var u in Unit.Units)
                {
                    if (extra >= 3) break;
                    if (u == p.focus || u.team != Team.Enemy || !u.Alive) continue;
                    if ((u.transform.position - fp).sqrMagnitude > 12f * 12f) continue;
                    Projectile.Fire(p, u, tip + Vector3.up * (0.25f * (extra + 1)), dmg * 0.8f, Soul, 30f, 0f, 0.24f);
                    extra++;
                }
                return 0.42f;
            }
            // 영혼 폭풍: 겨눈 곳에 쏟아지는 영혼의 비
            Vector3 c = AimGround(p, cam, 70f);
            Vector2 r = Random.insideUnitCircle * 5f;
            Vector3 at = OnGround(new Vector3(c.x + r.x, c.y, c.z + r.y)) + Vector3.up * 0.2f;
            Projectile.FireAt(p, Team.Enemy, at + new Vector3(r.y * 0.4f, 24f, -r.x * 0.4f), at, dmg * 0.6f, Soul, 75f, 2.6f, 0.4f);
            return 0.15f;
        }

        // ───────────── 강공격 ─────────────
        public static bool Spear(PlayerCtl p, Transform cam)
        {
            int lv = p.level;
            if (p.tier == 0)
            {
                if (p.focus == null) return false;
                Projectile.Fire(p, p.focus, p.rig.staffTip.position, 70f + 8f * lv, Bone, 36f, 3.2f, 0.5f);
                return true;
            }
            if (p.tier == 1)
            {
                // 뼈 창 비: 하늘에서 수십 개가 꽂힌다
                Vector3 c = AimGround(p, cam, 50f);
                Fx.Ring(c, 7f, Bone, 1.5f);
                Timed.Run(26, 0.05f, i =>
                {
                    Vector2 r = Random.insideUnitCircle * 7f;
                    Vector3 at = OnGround(new Vector3(c.x + r.x, c.y, c.z + r.y));
                    Projectile.FireAt(p, Team.Enemy, at + new Vector3(2f, 22f, -2f), at, 26f + 3f * lv, Bone, 65f, 2.4f, 0.35f);
                    if (i % 6 == 0) OrbitCam.Shake(0.25f);
                });
                return true;
            }
            // 거신의 척추: 땅에서 솟는 거대한 뼈 기둥이 일직선을 관통한다
            Vector3 target = AimGround(p, cam, 60f);
            Vector3 dir = Util.Flat(target - p.transform.position);
            if (dir.sqrMagnitude < 4f) dir = Util.Flat(cam.forward);
            dir.Normalize();
            Vector3 start = p.transform.position + dir * 4f;
            Game.I.Slow(0.25f, 0.35f);
            Hud.Flash(Bone, 0.35f);
            Timed.Run(13, 0.045f, i =>
            {
                Vector3 q = OnGround(start + dir * (i * 3.6f));
                Fx.Pillar(q, 7f + (i % 3) * 1.5f, 1.1f, Bone, 1.5f);
                Fx.Burst(q + Vector3.up, 4.5f, Bone, 0.3f);
                Combat.Area(p, q, 4.5f, 150f + 14f * lv, Team.Enemy);
                OrbitCam.Shake(0.55f);
            });
            return true;
        }

        // ───────────── 시체 활용 ─────────────
        public static bool Blast(PlayerCtl p)
        {
            int lv = p.level;
            Vector3 pp = p.transform.position;
            Vector3 center = p.focus != null ? p.focus.transform.position : pp;
            float reach = p.tier == 2 ? 45f : 32f;
            corpses.Clear();
            foreach (var c in Corpse.All)
            {
                // 영웅·보스 시체는 지배용으로 남긴다
                if (c.def.grade == UnitGrade.Hero || c.def.grade == UnitGrade.Boss) continue;
                if ((c.transform.position - pp).sqrMagnitude > reach * reach) continue;
                corpses.Add(c);
            }
            if (corpses.Count == 0) return false;

            if (p.tier == 2) return TideOfDead(p, lv);

            // 시체 폭발(6구) / 연쇄 폭발(10구, 터진 자리의 적이 죽으면 또 터진다)
            corpses.Sort((a, b) => (a.transform.position - center).sqrMagnitude.CompareTo((b.transform.position - center).sqrMagnitude));
            int n = Mathf.Min(p.tier == 1 ? 10 : 6, corpses.Count);
            for (int i = 0; i < n; i++)
            {
                Vector3 at = corpses[i].transform.position + Vector3.up * 0.5f;
                corpses[i].Consume();
                Explode(p, at, 5.5f, 55f + 6f * lv, p.tier == 1 ? 2 : 0);
            }
            OrbitCam.Shake(p.tier == 1 ? 0.45f : 0.25f);
            return true;
        }

        static void Explode(PlayerCtl p, Vector3 pos, float radius, float dmg, int chain)
        {
            Fx.Burst(pos, radius, Rot, 0.4f);
            if (chain <= 0)
            {
                Combat.Area(p, pos, radius, dmg, Team.Enemy);
                return;
            }
            buf.Clear();
            foreach (var u in Unit.Units)
            {
                if (u.team != Team.Enemy || u.IsDead) continue;
                float r = radius + u.Radius;
                if ((u.transform.position - pos).sqrMagnitude <= r * r) buf.Add(u);
            }
            for (int i = 0; i < buf.Count; i++)
            {
                var u = buf[i];
                Vector3 at = u.transform.position + Vector3.up * 0.5f;
                Combat.Deal(p, u, dmg);
                if (!u.IsDead) continue;
                Timed.Run(1, 0f, _ => Explode(p, at, radius * 0.85f, dmg * 0.8f, chain - 1), 0.22f);
            }
        }

        // 망자의 해일: 전장의 시체가 한꺼번에 일어나 가까운 적에게 돌진한 뒤 폭발한다
        static bool TideOfDead(PlayerCtl p, int lv)
        {
            int n = 0;
            for (int i = 0; i < corpses.Count; i++)
            {
                var c = corpses[i];
                Vector3 cp = c.transform.position;
                Unit best = null;
                float bd = 40f * 40f;
                foreach (var u in Unit.Units)
                {
                    if (u.team != Team.Enemy || !u.Alive) continue;
                    float d = (u.transform.position - cp).sqrMagnitude;
                    if (d < bd) { bd = d; best = u; }
                }
                if (best == null) continue;
                Fx.Burst(cp + Vector3.up, 1.6f * c.def.size, Tide, 0.4f);
                Projectile.FireAt(p, Team.Enemy, cp + Vector3.up, best.transform.position + Vector3.up * 0.6f,
                                  90f + 8f * lv, Tide, 17f + Random.Range(0f, 5f), 5f, 0.9f);
                c.Consume();
                n++;
            }
            if (n == 0) return false;
            OrbitCam.Shake(0.6f);
            Hud.Flash(Tide, 0.4f);
            return true;
        }

        // ───────────── 왕관 스킬 ─────────────
        // 망자의 군세 (소환학): 30초 동안 땅에서 해골 대군이 솟아나 함께 돌격한다. 영혼 슬롯을 쓰지 않는다.
        public static bool Legion(PlayerCtl p)
        {
            var def = Db.Get("skeleton");
            Vector3 pp = p.transform.position;
            Vector3 fwd = p.transform.forward;
            int made = 0;
            for (int i = 0; i < 28; i++)
            {
                float ang = (i % 14 - 6.5f) * 13f;
                float dist = 5f + (i / 14) * 3f + Random.Range(0f, 1.5f);
                Vector3 q = pp + Quaternion.Euler(0f, ang, 0f) * fwd * dist;
                q.y = pp.y;
                bool sky = World.OnSky(q);
                if (World.OnSky(pp) != sky) continue;
                q = OnGround(q);
                if (q.y < 0.3f && !sky) continue;
                var u = Unit.Create(def, Team.Player, q);
                u.MakeTemp(LegionTime + Random.Range(0f, 1.5f), i);
                u.transform.rotation = Quaternion.LookRotation(fwd);
                u.PlayRise();
                Fx.Burst(q + Vector3.up * 0.5f, 1.4f, Soul, 0.5f);
                made++;
            }
            if (made == 0) return false;
            Fx.Ring(pp, 14f, Soul, 1.2f);
            Game.I.Slow(0.5f, 0.3f);
            Hud.Flash(Soul, 0.7f);
            OrbitCam.Shake(1f);
            return true;
        }

        // 강림 (본드래곤): 타고 있지 않을 때 부르면 하늘에서 내려와 일직선을 브레스로 폭격한다
        public static bool Descent(PlayerCtl p, Transform cam, Unit dragon)
        {
            Vector3 dir = Util.Flat(cam.forward);
            if (dir.sqrMagnitude < 0.01f) dir = p.transform.forward;
            dir.Normalize();
            Strafe.Begin(p, dragon, p.transform.position + dir * 5f, dir);
            Game.I.Slow(0.35f, 0.35f);
            Hud.Flash(Soul, 0.5f);
            return true;
        }
    }
}
