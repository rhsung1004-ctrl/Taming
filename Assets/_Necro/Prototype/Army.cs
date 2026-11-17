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

        public float RaiseRange { get { return Spells.RaiseRange[game.player.tier]; } }
        // 왕관의 부름(금주)은 지배 마나가 절반
        public float RaiseMana(UnitGrade g) { return Db.RaiseMana(g) * (game.player.tier >= 2 ? 0.5f : 1f); }
        public static readonly Color Soul = new Color(0.72f, 0.45f, 1f);

        public readonly List<Unit> units = new List<Unit>();
        public int mode;
        public int bonusSlots;
        public Unit dragon;
        public bool hasPoint;            // 지점 사수: 마우스 가운데 버튼으로 찍은 자리를 지킨다
        public Vector3 point;

        // 정예 이상은 길게 눌러 지배한다
        public Corpse holdTarget;
        public float holdT, holdNeed;

        Vector3 formFwd = Vector3.forward, holdFwd = Vector3.forward;
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
                if (hasPoint) ClearPoint("군단이 다시 따라와요. (" + ModeName[mode] + ")");
                else
                {
                    mode = (mode + 1) % 3;
                    Hud.Toast(ModeDesc[mode], 2.5f);
                }
            }
            if (In.PointDown && units.Count > 0 && !pl.Riding)
            {
                point = Spells.AimGround(pl, game.cam.transform, 70f);
                hasPoint = true;
                holdFwd = Util.Flat(point - pl.transform.position);
                holdFwd = holdFwd.sqrMagnitude > 0.01f ? holdFwd.normalized : pl.transform.forward;
                Fx.Ring(point, 5f, new Color(0.5f, 0.75f, 1f), 1.2f);
                Fx.Pillar(point, 5f, 0.12f, new Color(0.5f, 0.75f, 1f), 1.2f, true);
                Hud.Toast("군단을 그 자리로 보냈어요. 근처의 적만 상대하며 지켜요. F를 누르면 다시 따라와요.", 3.5f);
            }

            // 정예 이상을 지배하는 동안에는 무릎을 굽히고 손을 내민다
            pl.rig.reach = Mathf.MoveTowards(pl.rig.reach, holdTarget != null ? 1f : 0f, dt * 5f);

            if (In.RaiseDown) BeginRaise();
            if (holdTarget != null)
            {
                bool lost = !In.RaiseHeld ||
                            Vector3.Distance(holdTarget.transform.position, pl.transform.position) > 16f;
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
            int tier = pl.tier;
            float range = RaiseRange;
            Corpse big = null;
            float bigD = float.MaxValue;
            bool any = false;
            // 일반 시체는 한 번에 모두 일으키고, 정예 이상은 가장 가까운 하나를 길게 눌러 지배
            var list = new List<Corpse>(Corpse.All);
            foreach (var c in list)
            {
                float d = Vector3.Distance(c.transform.position, pp);
                if (d > range) continue;
                any = true;
                // 일반은 즉시. 왕관의 부름(금주)이면 정예도 즉시
                if (c.def.grade == UnitGrade.Common || (tier >= 2 && c.def.grade == UnitGrade.Elite))
                {
                    if (TryRaise(c, false)) raised++;
                }
                else if (d < bigD && d <= 14f) { bigD = d; big = c; }
            }
            if (big != null)
            {
                holdTarget = big;
                holdT = 0f;
                holdNeed = Db.RaiseHold(big.def.grade);
            }
            else if (!any) Warn("근처에 시체가 없어요. 적을 쓰러뜨리면 시체가 남아요.");
            if (raised >= 4 && tier >= 1)
            {
                Fx.Ring(pp, Mathf.Min(range, 30f), Soul, 0.8f);
                OrbitCam.Shake(tier >= 2 ? 0.6f : 0.3f);
                if (tier >= 2) Hud.Flash(Soul, 0.5f);
            }
        }

        void Warn(string s)
        {
            if (warnT > 0f) return;
            warnT = 2f;
            Hud.Toast(s, 2.5f);
        }

        public void ClearPoint(string msg)
        {
            hasPoint = false;
            if (msg != null) Hud.Toast(msg, 2.5f);
        }

        // 죽음의 영역: 마나 없이, 슬롯이 남아 있으면 바로 군단에 들어온다
        public bool RaiseFree(Corpse c)
        {
            float keep = game.player.mana;
            game.player.mana = 9999f;
            bool ok = TryRaise(c, false);
            game.player.mana = keep;
            return ok;
        }

        bool TryRaise(Corpse c, bool makeRoom)
        {
            var pl = game.player;
            var d = c.def;
            int cost = Db.SlotCost(d.grade);
            float mana = RaiseMana(d.grade);
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
            Bond.OnRaised(u);
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
                if (u.rec != null && u.rec.name != null) continue;      // 이름 붙은 고참은 내보내지 않는다
                Fx.Burst(u.AimPoint, 1.2f, new Color(0.5f, 0.3f, 0.8f));
                units.RemoveAt(i);
                Object.Destroy(u.gameObject);
                freed++;
            }
            if (freed > 0) Hud.Toast("영혼 슬롯을 비우려고 일반 소환수 " + freed + "마리를 해방했어요.", 3.5f);
        }

        // 군단 강화(공격력·회복) / 광란(+공격 속도, 쓰러져도 잠시 더 싸움) / 불사의 군단(+일정 시간 죽지 않음)
        public bool Buff(int tier)
        {
            int n = 0;
            float time = tier == 0 ? 8f : 10f;
            Color c = tier == 2 ? new Color(1f, 0.85f, 0.4f) : new Color(1f, 0.3f, 0.35f);
            foreach (var u in Unit.Units)
            {
                if (!u.Ally || !u.Alive) continue;
                u.buffTimer = time;
                if (tier >= 1) u.frenzyTimer = time;
                if (tier >= 2) u.undyingTimer = 8f;
                u.Heal(u.maxHp * 0.3f);
                Fx.Burst(u.AimPoint, 1.2f * u.def.size, c, 0.3f);
                n++;
            }
            return n > 0;
        }

        // 주인공 뒤에 줄지어 서는 자리
        public Vector3 SlotPosition(Unit u)
        {
            if (u.temp)
            {
                // 망자의 군세는 주인공 앞쪽에 부채꼴로 선다
                int t = u.tempIndex;
                return game.player.transform.position + Quaternion.Euler(0f, (t % 14 - 6.5f) * 13f, 0f) * formFwd * (5f + (t / 14) * 3f);
            }
            int i = units.IndexOf(u);
            if (i < 0) i = 0;
            int row = i / 6, col = i % 6;
            Vector3 right = Vector3.Cross(Vector3.up, formFwd);
            if (hasPoint) return point - holdFwd * (row * 2.1f - 2f) + Vector3.Cross(Vector3.up, holdFwd) * ((col - 2.5f) * 1.9f);
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
                string n = u.def.NameFor(true);
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
