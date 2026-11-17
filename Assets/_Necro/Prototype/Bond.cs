using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 소환수 한 마리의 전적. 정예 이상은 지배할 때 이름을 받고, 일반 소환수는 고참이 되면 이름을 얻는다.
    public class Record
    {
        public string name;          // null이면 아직 이름 없는 소환수
        public string unitName;
        public UnitGrade grade;
        public int level = 1;
        public int battles, kills;
        public int featRank = -1;    // 가장 큰 전공의 등급 (쓰러뜨린 적 중 가장 높은 등급)
        public string feat;
        public bool veteran;

        public string Title { get { return name != null ? name + " (" + unitName + ")" : unitName; } }

        public string Summary
        {
            get
            {
                string s = "함께한 전투 " + battles + " · 처치 " + kills;
                if (feat != null) s += " · " + feat;
                return s;
            }
        }
    }

    // 거점 묘비에 새겨진 이름
    public class Fallen
    {
        public Record rec;
        public Vector3 pos;
    }

    // 군단과의 유대: 이름과 전적, 고참, 쓰러질 때의 한마디, 추모 묘비.
    // 주인공이 망자를 도구가 아니라 자기가 거둔 아이들처럼 아낀다는 점을 시스템으로 보여 준다.
    public static class Bond
    {
        public const int VeteranBattles = 5, VeteranKills = 8;
        const int MaxGraves = 24;

        public static readonly List<Fallen> Memorial = new List<Fallen>();

        static readonly string[] Names =
        {
            "하르", "벨로", "오닉", "세린", "카덴", "루모", "테오란", "이든", "마렌", "노아르",
            "실바", "그렌", "아슈", "루벤", "도란", "미르", "에녹", "타린", "보렌", "유르",
            "네브", "칼로", "소렌", "위든", "바란", "리오르", "헤일", "모아", "제른", "아델"
        };
        static readonly List<string> free = new List<string>();

        static readonly string[] FallenLines =
        {
            "수고했어. 조금만 쉬어.",
            "이제 쉬어도 돼.",
            "잘 싸웠어. 네 자리는 비워 둘게.",
            "고마웠어. 편히 잠들렴.",
            "끝까지 곁에 있어 줬구나. 고마워.",
        };

        static float lineT = -99f, vetLineT = -99f;
        static int lineIdx;
        static bool firstRaise;

        public static void Reset()
        {
            Memorial.Clear();
            free.Clear();
            free.AddRange(Names);
            lineT = vetLineT = -99f;
            lineIdx = 0;
            firstRaise = false;
        }

        public static string NewName()
        {
            if (free.Count == 0) free.AddRange(Names);
            int i = Random.Range(0, free.Count);
            string n = free[i];
            free.RemoveAt(i);
            return n;
        }

        // ───────────── 지배 ─────────────
        public static void OnRaised(Unit u)
        {
            var d = u.def;
            u.rec = new Record { unitName = d.NameFor(true), grade = d.grade };
            if (d.grade == UnitGrade.Elite || d.grade == UnitGrade.Hero || (d.grade == UnitGrade.Boss && !d.mount)) u.rec.name = NewName();

            if (d.mount) Story.Play("dragon_raise");
            else if (d.id == "boss") Story.Play("keeper_raise");
            else if (d.id == "lord") Story.Play("lord_raise");
            else if (d.grade == UnitGrade.Elite)
                Hud.Say("me", "손을 잡으렴. 오늘부터 네 이름은 " + Util.IyaYa(u.rec.name) + ".");
            else if (!firstRaise) Story.Play("first_raise");
            firstRaise = true;
        }

        // ───────────── 전적 ─────────────
        public static void OnKill(Unit u, Unit victim)
        {
            var r = u.rec;
            if (r == null) return;
            r.kills++;
            int rank = (int)victim.def.grade;
            if (rank > r.featRank && rank >= (int)UnitGrade.Elite)
            {
                r.featRank = rank;
                r.feat = victim.def.name + " 처치";
            }
            CheckVeteran(u);
        }

        // 오래 살아남은 소환수는 '고참'이 된다: 표시와 작은 능력치 보너스. 이름이 없었다면 이름도 얻는다.
        public static void CheckVeteran(Unit u)
        {
            var r = u.rec;
            if (r == null || r.veteran) return;
            if (r.battles < VeteranBattles && r.kills < VeteranKills) return;
            r.veteran = true;
            if (r.name == null && !u.def.mount) r.name = NewName();
            u.ApplyVeteran();
            Hud.Popup(u.AimPoint + Vector3.up * 0.8f, "★ 고참 " + u.DisplayName, new Color(1f, 0.82f, 0.35f), true);
            if (Time.time - vetLineT > 25f)
            {
                vetLineT = Time.time;
                Hud.Say("me", "오래 곁에 있어 줬구나, " + u.DisplayName + ". 고마워.");
            }
        }

        // ───────────── 쓰러짐과 추모 ─────────────
        public static void OnFallen(Unit u)
        {
            var r = u.rec;
            if (r == null) return;
            bool notable = r.grade != UnitGrade.Common || r.veteran;
            if (!notable) return;       // 전투 중에 자주 나오면 시끄러우므로 정예 이상이거나 고참일 때만

            if (u.def.mount)
            {
                Hud.Say("me", "조금만 쉬어. 금방 다시 불러 줄게.");
                return;
            }
            if (u.def.id == "lord") Hud.Say("me", "끝까지 명을 지켜 줬구나, " + r.name + ". 이제 쉬어도 돼.");
            else if (u.def.id == "boss") Hud.Say("me", "묘지는 내가 지킬게, " + r.name + ". 이제 쉬어도 돼.");
            else if (Time.time - lineT > 10f)
            {
                lineT = Time.time;
                string line = FallenLines[lineIdx++ % FallenLines.Length];
                Hud.Say("me", r.name != null ? r.name + "… " + line : line);
            }
            if (r.name != null) AddGrave(r);
        }

        // 이름 붙인 소환수를 잃으면 봉인의 제단 둘레에 묘비가 선다
        static void AddGrave(Record r)
        {
            int i = Memorial.Count;
            if (i >= MaxGraves) return;
            Vector3 c = World.At(World.StartXZ, 0f, 7f);
            float ang = (i * 37f + 20f) * Mathf.Deg2Rad;
            float rad = 7.5f + (i / 9) * 2.6f;
            float x = c.x + Mathf.Cos(ang) * rad, z = c.z + Mathf.Sin(ang) * rad;
            Vector3 p = new Vector3(x, World.Height(x, z), z);
            float yaw = Mathf.Atan2(c.x - x, c.z - z) * Mathf.Rad2Deg;
            World.Grave(p, yaw, 0);
            Util.Part(PrimitiveType.Sphere, null, p + Vector3.up * 1.25f, Vector3.one * 0.16f, new Color(0.72f, 0.45f, 1f), default(Vector3), true);
            Memorial.Add(new Fallen { rec = r, pos = p });
            Hud.Toast("제단 곁에 " + Util.EulReul(r.name) + " 기리는 묘비가 세워졌어요.", 4f);
        }
    }
}
