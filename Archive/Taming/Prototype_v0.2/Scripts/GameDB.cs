using System.Collections.Generic;
using UnityEngine;

public enum Element { Fire, Water, Grass, Earth, Wind }
public enum Role { Tank, Melee, Ranged, Support }
public enum MountType { None, Ground, Fly }
public enum Food { Jelly, Meat, Seed, Berry }
public enum BodyShape { Slime, Quadruped, Bird, Lizard }

// 몬스터 종 데이터. 나중에 ScriptableObject나 JSON으로 옮기면 됨.
public class SpeciesDef
{
    public string id;
    public string name;
    public string grade;
    public Element element;
    public Role role;
    public BodyShape shape;
    public Color color;
    public float size = 1f;

    public float hp;
    public float atk;
    public float moveSpeed;
    public float attackRange;
    public float attackCooldown;
    public bool ranged;
    public bool aggressive;

    public MountType mount;
    public int flyTier;      // 비행 단계 (1 = 깃털 새, 2 = 그리폰 ...)
    public float rideSpeed;

    public Food favorite;
    public float baseTameChance;
}

public static class GameDB
{
    public static readonly Dictionary<string, SpeciesDef> Species = new Dictionary<string, SpeciesDef>();
    public static readonly HashSet<string> RevealedFavorites = new HashSet<string>();

    static GameDB()
    {
        Add(new SpeciesDef
        {
            id = "fox", name = "아기 불여우", grade = "고급",
            element = Element.Fire, role = Role.Melee, shape = BodyShape.Quadruped,
            color = new Color(1f, 0.55f, 0.2f), size = 0.75f,
            hp = 120, atk = 14, moveSpeed = 6.5f, attackRange = 1.8f, attackCooldown = 1f,
            aggressive = false, mount = MountType.None,
            favorite = Food.Berry, baseTameChance = 0.5f
        });
        Add(new SpeciesDef
        {
            id = "slime", name = "젤리 슬라임", grade = "일반",
            element = Element.Grass, role = Role.Tank, shape = BodyShape.Slime,
            color = new Color(0.45f, 0.85f, 0.45f), size = 1f,
            hp = 140, atk = 8, moveSpeed = 3f, attackRange = 1.6f, attackCooldown = 1.4f,
            aggressive = false, mount = MountType.None,
            favorite = Food.Jelly, baseTameChance = 0.6f
        });
        Add(new SpeciesDef
        {
            id = "wolf", name = "들늑대", grade = "고급",
            element = Element.Wind, role = Role.Melee, shape = BodyShape.Quadruped,
            color = new Color(0.6f, 0.62f, 0.68f), size = 1.2f,
            hp = 160, atk = 16, moveSpeed = 7f, attackRange = 2f, attackCooldown = 1.1f,
            aggressive = true, mount = MountType.Ground, rideSpeed = 13f,
            favorite = Food.Meat, baseTameChance = 0.4f
        });
        Add(new SpeciesDef
        {
            id = "bird", name = "깃털 새", grade = "고급",
            element = Element.Wind, role = Role.Ranged, shape = BodyShape.Bird,
            color = new Color(0.45f, 0.75f, 1f), size = 1f,
            hp = 90, atk = 10, moveSpeed = 6f, attackRange = 9f, attackCooldown = 1.5f, ranged = true,
            aggressive = false, mount = MountType.Fly, flyTier = 1, rideSpeed = 14f,
            favorite = Food.Seed, baseTameChance = 0.5f
        });
        Add(new SpeciesDef
        {
            id = "lizard", name = "불꽃 도마뱀", grade = "고급",
            element = Element.Fire, role = Role.Ranged, shape = BodyShape.Lizard,
            color = new Color(0.9f, 0.3f, 0.25f), size = 1f,
            hp = 130, atk = 14, moveSpeed = 5f, attackRange = 8f, attackCooldown = 1.6f, ranged = true,
            aggressive = true, mount = MountType.None,
            favorite = Food.Meat, baseTameChance = 0.45f
        });
        Add(new SpeciesDef
        {
            id = "griffon", name = "그리폰", grade = "희귀",
            element = Element.Wind, role = Role.Melee, shape = BodyShape.Bird,
            color = new Color(0.95f, 0.78f, 0.35f), size = 1.9f,
            hp = 320, atk = 22, moveSpeed = 8f, attackRange = 2.6f, attackCooldown = 1.2f,
            aggressive = true, mount = MountType.Fly, flyTier = 2, rideSpeed = 22f,
            favorite = Food.Meat, baseTameChance = 0.25f
        });
    }

    static void Add(SpeciesDef d) { Species[d.id] = d; }

    public static SpeciesDef Get(string id) { return Species[id]; }

    // 불 > 풀 > 대지 > 바람 > 물 > 불
    static bool Beats(Element a, Element b)
    {
        return (a == Element.Fire && b == Element.Grass)
            || (a == Element.Grass && b == Element.Earth)
            || (a == Element.Earth && b == Element.Wind)
            || (a == Element.Wind && b == Element.Water)
            || (a == Element.Water && b == Element.Fire);
    }

    public static float ElementMultiplier(Element attacker, Element defender)
    {
        if (Beats(attacker, defender)) return 1.5f;
        if (Beats(defender, attacker)) return 0.7f;
        return 1f;
    }

    public static string ElementName(Element e)
    {
        switch (e)
        {
            case Element.Fire: return "불";
            case Element.Water: return "물";
            case Element.Grass: return "풀";
            case Element.Earth: return "대지";
            default: return "바람";
        }
    }

    public static Color ElementColor(Element e)
    {
        switch (e)
        {
            case Element.Fire: return new Color(1f, 0.45f, 0.15f);
            case Element.Water: return new Color(0.3f, 0.55f, 1f);
            case Element.Grass: return new Color(0.4f, 0.9f, 0.3f);
            case Element.Earth: return new Color(0.65f, 0.45f, 0.25f);
            default: return new Color(0.75f, 0.95f, 1f);
        }
    }

    public static string FoodName(Food f)
    {
        switch (f)
        {
            case Food.Jelly: return "젤리";
            case Food.Meat: return "생고기";
            case Food.Seed: return "씨앗";
            default: return "열매";
        }
    }

    // 비행 단계별 최대 고도 (월드 y 좌표)
    public static float FlyCeiling(int tier)
    {
        if (tier >= 2) return 75f;
        if (tier == 1) return 26f;
        return 0f;
    }
}
