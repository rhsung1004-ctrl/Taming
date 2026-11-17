using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    public enum Shape { Skeleton, Archer, Wolf, Knight, Keeper, Dragon, Lord }

    // 프로토타입용 유닛 정의. 이름·등급·슬롯 규칙은 2D판(사령술사 키우기)과 같다.
    // 본편에서는 Necro.UnitData(ScriptableObject)로 옮긴다.
    public class UnitDef
    {
        public string id, name, allyName;
        public UnitGrade grade;
        public Shape shape;
        public float size = 1f;
        public float hp, atk, speed, range, cooldown;
        public bool ranged;
        public float aggro = 14f;
        public int xp;
        public bool mount;       // 지배하면 탈것이 된다 (고룡 → 본드래곤)
        public string evolvesTo; // 소환수로 evolveLevel에 도달하면 이 유닛으로 진화 (2D판 evolves_to)
        public int evolveLevel = 3;

        public string NameFor(bool ally) { return ally && allyName != null ? allyName : name; }
    }

    public static class Db
    {
        public static readonly Dictionary<string, UnitDef> Units = new Dictionary<string, UnitDef>();

        static Db()
        {
            Add(new UnitDef { id = "skeleton", name = "해골 병사", grade = UnitGrade.Common, shape = Shape.Skeleton,
                hp = 60, atk = 8, speed = 4.5f, range = 1.8f, cooldown = 1.1f, xp = 6, evolvesTo = "skelknight" });
            Add(new UnitDef { id = "archer", name = "해골 궁수", grade = UnitGrade.Common, shape = Shape.Archer,
                hp = 42, atk = 9, speed = 4.2f, range = 14f, cooldown = 1.7f, ranged = true, aggro = 17f, xp = 7, evolvesTo = "sniper" });
            Add(new UnitDef { id = "wolf", name = "늑대", grade = UnitGrade.Common, shape = Shape.Wolf, size = 0.95f,
                hp = 45, atk = 7, speed = 7.5f, range = 1.7f, cooldown = 0.9f, xp = 5, evolvesTo = "shadewolf" });
            // 1장 보스 (2D판 id: lord). 프로토타입에서는 부유 성채에서 왕관 조각을 지킨다
            Add(new UnitDef { id = "lord", name = "망자의 군주", grade = UnitGrade.Boss, shape = Shape.Lord, size = 2.1f,
                hp = 2600, atk = 36, speed = 3.9f, range = 3.4f, cooldown = 1.5f, aggro = 24f, xp = 300 });
            // 진화형 (2D판과 같은 id·이름)
            Add(new UnitDef { id = "skelknight", name = "해골 기사", grade = UnitGrade.Common, shape = Shape.Skeleton, size = 1.18f,
                hp = 120, atk = 14, speed = 4.7f, range = 1.9f, cooldown = 1f, xp = 12 });
            Add(new UnitDef { id = "sniper", name = "뼈 저격수", grade = UnitGrade.Common, shape = Shape.Archer, size = 1.12f,
                hp = 75, atk = 17, speed = 4.3f, range = 19f, cooldown = 1.6f, ranged = true, aggro = 20f, xp = 12 });
            Add(new UnitDef { id = "shadewolf", name = "그림자 늑대", grade = UnitGrade.Common, shape = Shape.Wolf, size = 1.2f,
                hp = 85, atk = 12, speed = 8.3f, range = 1.8f, cooldown = 0.8f, xp = 12 });
            Add(new UnitDef { id = "knight", name = "망령 기사", grade = UnitGrade.Elite, shape = Shape.Knight, size = 1.3f,
                hp = 260, atk = 20, speed = 4.4f, range = 2.4f, cooldown = 1.4f, xp = 25 });
            Add(new UnitDef { id = "boss", name = "묘지기", grade = UnitGrade.Hero, shape = Shape.Keeper, size = 1.8f,
                hp = 1100, atk = 30, speed = 3.9f, range = 3f, cooldown = 1.6f, aggro = 18f, xp = 120 });
            Add(new UnitDef { id = "dragon", name = "잠들지 못한 고룡", allyName = "본드래곤", grade = UnitGrade.Boss, shape = Shape.Dragon, size = 3f,
                hp = 3200, atk = 42, speed = 5f, range = 6f, cooldown = 1.7f, aggro = 26f, xp = 400, mount = true });
        }

        static void Add(UnitDef d) { Units[d.id] = d; }
        public static UnitDef Get(string id) { return Units[id]; }

        // 2D판 balance.gd와 같은 규칙
        public static int SlotCost(UnitGrade g)
        {
            switch (g) { case UnitGrade.Elite: return 3; case UnitGrade.Hero: return 4; case UnitGrade.Boss: return 6; default: return 1; }
        }
        public static float RaiseMana(UnitGrade g)
        {
            switch (g) { case UnitGrade.Elite: return 22f; case UnitGrade.Hero: return 32f; case UnitGrade.Boss: return 50f; default: return 8f; }
        }
        public static float RaiseHold(UnitGrade g)
        {
            switch (g) { case UnitGrade.Elite: return 1.2f; case UnitGrade.Hero: return 1.6f; case UnitGrade.Boss: return 2.2f; default: return 0f; }
        }
        // 시체가 남아 있는 시간. 3D에서는 걸어가서 지배해야 하므로 2D판보다 길게 잡았다. 보스는 사라지지 않는다.
        public static float CorpseTime(UnitGrade g)
        {
            switch (g) { case UnitGrade.Elite: return 40f; case UnitGrade.Hero: return 90f; case UnitGrade.Boss: return 99999f; default: return 25f; }
        }
        public static string GradeName(UnitGrade g)
        {
            switch (g) { case UnitGrade.Elite: return "정예"; case UnitGrade.Hero: return "영웅"; case UnitGrade.Boss: return "보스"; default: return "일반"; }
        }
        public static Color GradeColor(UnitGrade g)
        {
            switch (g)
            {
                case UnitGrade.Elite: return new Color(0.55f, 0.75f, 1f);
                case UnitGrade.Hero: return new Color(0.85f, 0.6f, 1f);
                case UnitGrade.Boss: return new Color(1f, 0.75f, 0.3f);
                default: return Color.white;
            }
        }
    }
}
