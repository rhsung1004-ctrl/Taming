using UnityEngine;

// 테이밍 3단계: 약화(체력 30% 이하) → 조건(먹이) → 교감 미니게임
public class TamingSystem : MonoBehaviour
{
    public const float TameRange = 8f;

    public bool active;
    public Monster target;
    public float needle, zoneCenter, zoneHalf, perfectHalf, speed, timeLeft;
    float dir = 1f;

    public float BaseChance(Monster m, float miniBonus)
    {
        float c = m.def.baseTameChance;
        c += Mathf.Clamp01((0.3f - m.hp / m.maxHp) / 0.3f) * 0.15f;   // 체력이 낮을수록 최대 +15%
        if (m.fedFavorite) c += 0.2f;
        c += GameState.Fondness(m.def.id);
        c += miniBonus;
        c -= (m.level - 1) * 0.03f;
        return Mathf.Clamp(c, 0.05f, 0.95f);
    }

    static float GradeSpeed(string grade)
    {
        switch (grade)
        {
            case "일반": return 1.1f;
            case "고급": return 1.4f;
            case "희귀": return 1.8f;
            case "영웅": return 2.2f;
            default: return 2.6f;
        }
    }

    public void Begin(Monster m)
    {
        if (active) return;
        var pl = GameManager.I.player;
        if (m == null || m.team != Team.Wild || m.IsDead)
        {
            GameHUD.Toast("테이밍할 몬스터를 먼저 터치해서 선택하세요.");
            return;
        }
        if (!m.Tameable)
        {
            GameHUD.Toast(Util.IGa(m.def.name) + " 아직 기운이 넘쳐요. 체력을 30% 이하로 깎으세요.");
            return;
        }
        if (Vector3.Distance(m.transform.position, pl.transform.position) > TameRange)
        {
            GameHUD.Toast("조금 더 가까이 가세요.");
            return;
        }
        active = true;
        target = m;
        m.lockedByTaming = true;
        m.calmTimer = 999f;
        speed = GradeSpeed(m.def.grade);
        zoneHalf = 0.09f;
        perfectHalf = 0.03f;
        zoneCenter = Random.Range(0.25f, 0.75f);
        needle = 0f;
        dir = 1f;
        timeLeft = 5f;
    }

    void Update()
    {
        if (!active) return;
        if (target == null || target.IsDead || target.team != Team.Wild)
        {
            Cancel();
            return;
        }
        float dt = Time.deltaTime;
        needle += dir * speed * dt;
        if (needle > 1f) { needle = 2f - needle; dir = -1f; }
        if (needle < 0f) { needle = -needle; dir = 1f; }
        timeLeft -= dt;
        if (timeLeft <= 0f) Resolve(1f);
    }

    public void Tap()
    {
        if (active) Resolve(Mathf.Abs(needle - zoneCenter));
    }

    void Resolve(float diff)
    {
        float mini;
        string grade;
        if (diff <= perfectHalf) { mini = 0.2f; grade = "완벽한 교감!"; }
        else if (diff <= zoneHalf) { mini = 0.08f; grade = "좋은 교감"; }
        else { mini = -0.15f; grade = "교감 실패"; }

        var m = target;
        active = false;
        target = null;
        m.lockedByTaming = false;
        m.calmTimer = 0f;

        float chance = BaseChance(m, mini);
        string pct = Mathf.RoundToInt(chance * 100f) + "%";
        if (Random.value < chance)
        {
            GameManager.I.OnTamed(m, grade + " (성공 확률 " + pct + ")");
        }
        else
        {
            GameState.AddFondness(m.def.id, 0.1f);
            m.hp = Mathf.Max(m.hp, m.maxHp * 0.4f);
            m.everTameable = false;
            m.target = GameManager.I.player;
            GameHUD.Popup(m.AimPoint + Vector3.up, "실패…", new Color(0.8f, 0.8f, 0.9f), true);
            GameHUD.Toast(grade + " — 테이밍 실패 (확률 " + pct + "). 호감도가 올라 다음엔 더 쉬워요!", 4.5f);
        }
    }

    public void Cancel()
    {
        if (target != null)
        {
            target.lockedByTaming = false;
            target.calmTimer = 0f;
        }
        active = false;
        target = null;
    }

    public void Feed(Monster m, Food f)
    {
        var pl = GameManager.I.player;
        if (m == null || m.team != Team.Wild || m.IsDead)
        {
            GameHUD.Toast("먹이를 줄 몬스터를 먼저 선택하세요.");
            return;
        }
        if (Vector3.Distance(m.transform.position, pl.transform.position) > 12f)
        {
            GameHUD.Toast("조금 더 가까이 가세요.");
            return;
        }
        if (GameState.food[f] <= 0)
        {
            GameHUD.Toast(Util.IGa(GameDB.FoodName(f)) + " 없어요.");
            return;
        }
        GameState.food[f]--;
        string fn = GameDB.FoodName(f);
        if (f == m.def.favorite)
        {
            m.fedFavorite = true;
            m.calmTimer = 6f;
            GameDB.RevealedFavorites.Add(m.def.id);
            GameHUD.Popup(m.AimPoint + Vector3.up, "♥", new Color(1f, 0.5f, 0.7f), true);
            GameHUD.Toast(Util.IGa(m.def.name) + " " + Util.EulReul(fn) + " 아주 좋아해요! 성공률 +20%, 잠시 얌전해집니다.", 4.5f);
        }
        else
        {
            m.calmTimer = 1.5f;
            GameHUD.Popup(m.AimPoint + Vector3.up, "…", Color.gray, false);
            GameHUD.Toast(Util.EunNeun(fn) + " 별로 안 좋아하는 것 같아요.");
        }
    }
}
