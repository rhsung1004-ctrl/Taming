using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 일정 시간 전장에 남는 왕관 스킬.
    //  죽음의 영역 (저주학): 영역 안의 적은 계속 약해지고, 그 안에서 죽으면 즉시 소환수가 된다
    //  역병의 안개 (맹독학): 감염된 적은 계속 피해를 입고, 가까운 적에게 옮기며, 쓰러지면 폭발한다
    public class CrownField : MonoBehaviour
    {
        public static CrownField Active;

        bool plague;
        PlayerCtl player;
        Vector3 center;
        float radius, life, tick;
        Transform disc;
        readonly List<Unit> infected = new List<Unit>();
        readonly List<Unit> buf = new List<Unit>();

        static readonly Color Curse = new Color(0.35f, 0.95f, 0.5f);
        static readonly Color Venom = new Color(0.7f, 1f, 0.25f);

        public static void Domain(PlayerCtl p, Vector3 center, float radius, float life)
        {
            var f = Make(p, center, radius, life, false);
            f.disc = Util.Part(PrimitiveType.Cylinder, f.transform, Vector3.up * 0.06f, new Vector3(radius * 2f, 0.02f, radius * 2f),
                               new Color(0.05f, 0.16f, 0.1f), default(Vector3), true);
            Fx.Ring(center, radius, Curse, 0.8f);
        }

        public static void Plague(PlayerCtl p, Vector3 center, float radius, float life)
        {
            var f = Make(p, center, radius, life, true);
            Fx.Ring(center, radius, Venom, 1f);
            foreach (var u in Unit.Units)
                if (u.team == Team.Enemy && u.Alive && (u.transform.position - center).sqrMagnitude < radius * radius) f.infected.Add(u);
        }

        static CrownField Make(PlayerCtl p, Vector3 center, float radius, float life, bool plague)
        {
            if (Active != null) Active.End();
            var g = new GameObject(plague ? "PlagueMist" : "DeathDomain");
            g.transform.position = center;
            var f = g.AddComponent<CrownField>();
            f.player = p;
            f.center = center;
            f.radius = radius;
            f.life = life;
            f.plague = plague;
            Active = f;
            return f;
        }

        void Update()
        {
            float dt = Time.deltaTime;
            life -= dt;
            tick -= dt;
            if (tick <= 0f)
            {
                tick = 0.5f;
                if (plague) PlagueTick();
                else DomainTick();
            }
            if (life <= 0f) End();
        }

        void DomainTick()
        {
            if (Mathf.FloorToInt(life) % 2 == 0) Fx.Ring(center, radius, Curse, 0.9f);
            float dmg = 12f + 2f * player.level;
            buf.Clear();
            foreach (var u in Unit.Units)
            {
                if (u.team != Team.Enemy || u.IsDead) continue;
                bool inside = (u.transform.position - center).sqrMagnitude < radius * radius;
                u.damageTakenMul = inside ? 1.5f : 1f;       // 영역 안에서는 받는 피해 +50%
                if (inside) buf.Add(u);
            }
            for (int i = 0; i < buf.Count; i++) Combat.Deal(player, buf[i], dmg);
            // 영역 안에 생긴 시체는 손을 내밀지 않아도 스스로 일어나 군단에 들어온다 (영웅·보스 제외)
            buf.Clear();
            var army = Game.I.army;
            for (int i = Corpse.All.Count - 1; i >= 0; i--)
            {
                var c = Corpse.All[i];
                if (c.def.grade == UnitGrade.Hero || c.def.grade == UnitGrade.Boss) continue;
                if ((c.transform.position - center).sqrMagnitude > radius * radius) continue;
                if (army.Free < Db.SlotCost(c.def.grade)) continue;
                army.RaiseFree(c);
            }
        }

        void PlagueTick()
        {
            float dmg = 10f + 1.5f * player.level;
            // 전염: 감염된 적 가까이 있는 적에게 옮는다
            buf.Clear();
            foreach (var u in Unit.Units)
            {
                if (u.team != Team.Enemy || !u.Alive || infected.Contains(u)) continue;
                for (int i = 0; i < infected.Count; i++)
                {
                    var s = infected[i];
                    if (s == null || s.IsDead) continue;
                    if ((s.transform.position - u.transform.position).sqrMagnitude < 5.5f * 5.5f) { buf.Add(u); break; }
                }
            }
            infected.AddRange(buf);

            for (int i = infected.Count - 1; i >= 0; i--)
            {
                var u = infected[i];
                if (u == null || u.IsDead) { infected.RemoveAt(i); continue; }
                Vector3 at = u.AimPoint;
                Fx.Burst(at, 0.9f * u.def.size, Venom, 0.25f);
                Combat.Deal(player, u, dmg);
                if (u.IsDead)
                {
                    // 쓰러진 감염자는 폭발한다
                    infected.RemoveAt(i);
                    Fx.Burst(at, 4.5f, Venom, 0.4f);
                    Combat.Area(player, at, 4.5f, 50f + 5f * player.level, Team.Enemy);
                }
            }
        }

        void End()
        {
            if (!plague)
                foreach (var u in Unit.Units)
                    if (u.team == Team.Enemy) u.damageTakenMul = 1f;
            if (Active == this) Active = null;
            Destroy(gameObject);
        }
    }
}
