using System.Collections.Generic;
using UnityEngine;

public enum Team { Player, Wild }

// 체력을 가진 모든 것(주인공, 펫, 야생 몬스터)의 공통 부모
public abstract class Combatant : MonoBehaviour
{
    public static readonly List<Combatant> All = new List<Combatant>();

    public Team team;
    public Element element;
    public bool neutral;          // true면 속성 상성 무시 (주인공)
    public float maxHp = 100f;
    public float hp = 100f;
    public float lastHurtTime = -99f;

    public bool IsDead { get { return hp <= 0f; } }
    public abstract string DisplayName { get; }
    public virtual Vector3 AimPoint { get { return transform.position + Vector3.up; } }

    protected virtual void OnEnable() { All.Add(this); }
    protected virtual void OnDisable() { All.Remove(this); }

    public virtual void TakeDamage(float amount, Combatant src)
    {
        if (IsDead) return;
        hp = Mathf.Max(0f, hp - amount);
        lastHurtTime = Time.time;
        if (hp <= 0f) Die(src);
    }

    public void Heal(float amount)
    {
        if (IsDead) return;
        hp = Mathf.Min(maxHp, hp + amount);
    }

    protected abstract void Die(Combatant killer);
}

public static class Combat
{
    public static void Deal(Combatant src, Combatant dst, float power, Element? el)
    {
        if (dst == null || dst.IsDead) return;
        float mul = 1f;
        if (el.HasValue && !dst.neutral) mul = GameDB.ElementMultiplier(el.Value, dst.element);
        float dmg = power * mul * Random.Range(0.9f, 1.1f);
        Vector3 at = dst.AimPoint + Vector3.up * 0.4f;
        dst.TakeDamage(dmg, src);

        Color c = dst.team == Team.Player ? new Color(1f, 0.45f, 0.45f) : Color.white;
        string s = Mathf.RoundToInt(dmg).ToString();
        if (mul > 1.01f) { c = new Color(1f, 0.6f, 0.1f); s += " 효과 굉장!"; }
        else if (mul < 0.99f) { c = new Color(0.7f, 0.7f, 0.7f); s += " 효과 별로"; }
        GameHUD.Popup(at, s, c, mul > 1.01f);
    }
}

public class Projectile : MonoBehaviour
{
    Combatant src, dst;
    float power;
    Element? el;
    float life = 3f;
    const float Speed = 20f;

    public static void Fire(Combatant src, Combatant dst, Vector3 from, float power, Element? el, Color color)
    {
        var g = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        Object.DestroyImmediate(g.GetComponent<Collider>());
        g.layer = 2;
        g.transform.position = from;
        g.transform.localScale = Vector3.one * 0.35f;
        g.GetComponent<Renderer>().sharedMaterial = Util.Glow(color);
        var p = g.AddComponent<Projectile>();
        p.src = src;
        p.dst = dst;
        p.power = power;
        p.el = el;
    }

    void Update()
    {
        life -= Time.deltaTime;
        if (dst == null || dst.IsDead || !dst.gameObject.activeInHierarchy || life <= 0f)
        {
            Destroy(gameObject);
            return;
        }
        Vector3 aim = dst.AimPoint;
        transform.position = Vector3.MoveTowards(transform.position, aim, Speed * Time.deltaTime);
        if ((transform.position - aim).sqrMagnitude < 0.25f)
        {
            Combat.Deal(src, dst, power, el);
            Destroy(gameObject);
        }
    }
}

// 보유 펫 한 마리의 저장 데이터
public class PetData
{
    public string speciesId;
    public int level = 1;
    public float exp;
    public bool inParty;
    public Monster instance;     // 파티에 있을 때 월드에 있는 몬스터
    public float reviveTimer;    // 기절 회복까지 남은 시간

    public SpeciesDef Def { get { return GameDB.Get(speciesId); } }
    public float ExpToNext { get { return 20f + level * 15f; } }
}

public static class GameState
{
    public const int MaxParty = 3;
    public static readonly List<PetData> pets = new List<PetData>();
    public static readonly Dictionary<Food, int> food = new Dictionary<Food, int>();
    static readonly Dictionary<string, float> fondness = new Dictionary<string, float>();

    public static void Reset()
    {
        pets.Clear();
        fondness.Clear();
        food.Clear();
        food[Food.Jelly] = 3;
        food[Food.Meat] = 3;
        food[Food.Seed] = 3;
        food[Food.Berry] = 3;
        GameDB.RevealedFavorites.Clear();
    }

    public static float Fondness(string id)
    {
        float v;
        return fondness.TryGetValue(id, out v) ? v : 0f;
    }

    public static void AddFondness(string id, float v)
    {
        fondness[id] = Mathf.Min(0.5f, Fondness(id) + v);
    }

    public static int PartyCount
    {
        get
        {
            int n = 0;
            foreach (var p in pets) if (p.inParty) n++;
            return n;
        }
    }

    public static bool Owns(string id)
    {
        foreach (var p in pets) if (p.speciesId == id) return true;
        return false;
    }
}
