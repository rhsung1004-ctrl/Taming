using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 군단: 영혼 슬롯, 시체 지배, 명령, 대형
    public class Army
    {
        public const int Charge = 0, Guard = 1, Retreat = 2;
        public static readonly string[] ModeName = { "돌격", "호위", "후퇴" };
        static readonly string[] ModeDesc = { "돌격: 주변의 적을 먼저 공격해요", "호위: 가까이 온 적만 상대해요", "후퇴: 싸우지 않고 따라와요" };

        public const float RaiseRange = 12f;
        public static readonly Color Soul = new Color(0.72f, 0.45f, 1f);

        public readonly List<Unit> units = new List<Unit>();
        public int mode;
        public int bonusSlots;
        public Unit dragon;

        // 정예 이상은 길게 눌러 지배한다
        public Corpse holdTarget;
        public float holdT, holdNeed;

        Vector3 formFwd = Vector3.forward;
        float warnT;

        Game game;
        public Army(Game g) { game = g; }

        public int MaxSlots { get { return 8 + (game.player.level - 1) + bonusSlots; } }
        public int UsedSlots
        {
            get
            {
                int n = 0;
                foreach (var u in units) n += Db.SlotCost(u.def.grade);
                return n;
            }
        }
        public int Free { get { return MaxSlots - UsedSlots; } }
        public int Count { get { return units.Count; } }

        public void Remove(Unit u)
        {
            units.Remove(u);
            if (dragon == u) dragon = null;
        }

        public void Tick(float dt)
        {
            var pl = game.player;
            units.RemoveAll(u => u == null);
            formFwd = Vector3.Slerp(formFwd, pl.transform.forward, dt * 2.5f);
            warnT -= dt;

            if (In.CommandDown)
            {
                mode = (mode + 1) % 3;
                Hud.Toast(ModeDesc[mode], 2.5f);
            }

            if (In.RaiseDown) BeginRaise();
            if (holdTarget != null)
            {
                bool lost = !In.RaiseHeld ||
                            Vector3.Distance(holdTarget.transform.position, pl.transform.position) > RaiseRange + 2f;
                if (lost) holdTarget = null;
                else
                {
                    holdT += dt;
                    if (holdT >= holdNeed)
                    {
                        var c = holdTarget;
                        holdTarget = null;
                        TryRaise(c, true);
                    }
                }
            }
        }

        void BeginRaise()
        {
            var pl = game.player;
            Vector3 pp = pl.transform.position;
            int raised = 0;
            Corpse big = null;
            float bigD = float.MaxValue;
            bool any = false;
            // 일반 시체는 한 번에 모두 일으키고, 정예 이상은 가장 가까운 하나를 길게 눌러 지배
            var list = new List<Corpse>(Corpse.All);
            foreach (var c in list)
            {
                float d = Vector3.Distance(c.transform.position, pp);
                if (d > RaiseRange) continue;
                any = true;
                if (c.def.grade == UnitGrade.Common)
                {
                    if (TryRaise(c, false)) raised++;
                }
                else if (d < bigD) { bigD = d; big = c; }
            }
            if (big != null)
            {
                holdTarget = big;
                holdT = 0f;
                holdNeed = Db.RaiseHold(big.def.grade);
            }
            else if (!any) Warn("근처에 시체가 없어요. 적을 쓰러뜨리면 시체가 남아요.");
        }

        void Warn(string s)
        {
            if (warnT > 0f) return;
            warnT = 2f;
            Hud.Toast(s, 2.5f);
        }

        bool TryRaise(Corpse c, bool makeRoom)
        {
            var pl = game.player;
            var d = c.def;
            int cost = Db.SlotCost(d.grade);
            float mana = Db.RaiseMana(d.grade);
            if (pl.mana < mana) { Warn("마나가 부족해요."); return false; }
            if (Free < cost && makeRoom) MakeRoom(cost);
            if (Free < cost)
            {
                Warn(makeRoom ? "영혼 슬롯이 부족해요 (" + cost + "칸 필요)." : "영혼 슬롯이 가득 찼어요. 레벨을 올리면 늘어나요.");
                return false;
            }
            pl.mana -= mana;
            var u = Unit.Create(d, Team.Player, c.transform.position);
            u.transform.rotation = c.transform.rotation;
            u.PlayRise();
            units.Add(u);
            Fx.Burst(c.transform.position + Vector3.up, 1.6f * d.size, Soul, 0.5f);
            Hud.Popup(u.AimPoint + Vector3.up * 0.6f, d.grade == UnitGrade.Common ? "지배!" : u.DisplayName + " 지배!", Soul, d.grade != UnitGrade.Common);
            c.Consume();
            if (d.mount) dragon = u;
            game.OnRaised(u);
            return true;
        }

        // 강한 망자를 들이려고 일반 소환수를 해방한다
        void MakeRoom(int cost)
        {
            int freed = 0;
            for (int i = units.Count - 1; i >= 0 && Free < cost; i--)
            {
                var u = units[i];
                if (u.def.grade != UnitGrade.Common) continue;
                Fx.Burst(u.AimPoint, 1.2f, new Color(0.5f, 0.3f, 0.8f));
                units.RemoveAt(i);
                Object.Destroy(u.gameObject);
                freed++;
            }
            if (freed > 0) Hud.Toast("영혼 슬롯을 비우려고 일반 소환수 " + freed + "마리를 해방했어요.", 3.5f);
        }

        public bool Buff()
        {
            if (units.Count == 0) return false;
            foreach (var u in units)
            {
                if (u == null || !u.Alive) continue;
                u.buffTimer = 8f;
                u.Heal(u.maxHp * 0.3f);
                Fx.Burst(u.AimPoint, 1.2f * u.def.size, new Color(1f, 0.3f, 0.35f), 0.3f);
            }
            return true;
        }

        // 주인공 뒤에 줄지어 서는 자리
        public Vector3 SlotPosition(Unit u)
        {
            int i = units.IndexOf(u);
            if (i < 0) i = 0;
            int row = i / 6, col = i % 6;
            Vector3 right = Vector3.Cross(Vector3.up, formFwd);
            return game.player.transform.position - formFwd * (3f + row * 2.1f) + right * ((col - 2.5f) * 1.9f);
        }

        // "해골 병사 4 · 망령 기사 1" 같은 요약
        public string Summary()
        {
            if (units.Count == 0) return "군단 없음";
            var counts = new Dictionary<string, int>();
            foreach (var u in units)
            {
                if (u == null) continue;
                string n = u.DisplayName;
                int c;
                counts.TryGetValue(n, out c);
                counts[n] = c + 1;
            }
            var sb = new System.Text.StringBuilder();
            foreach (var kv in counts)
            {
                if (sb.Length > 0) sb.Append(" · ");
                sb.Append(kv.Key).Append(' ').Append(kv.Value);
            }
            return sb.ToString();
        }
    }
}
