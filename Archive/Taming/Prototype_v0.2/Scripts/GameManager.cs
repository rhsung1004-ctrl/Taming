using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

// 빈 씬에서 Play를 누르면 자동으로 게임 전체를 만든다.
public static class Bootstrap
{
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Init()
    {
#if UNITY_2023_1_OR_NEWER
        if (Object.FindFirstObjectByType<GameManager>() != null) return;
#else
        if (Object.FindObjectOfType<GameManager>() != null) return;
#endif
        new GameObject("GameManager").AddComponent<GameManager>();
    }
}

public class GameManager : MonoBehaviour
{
    public static GameManager I;
    public static readonly string[] ModeShort = { "자유", "집중", "후퇴" };
    static readonly string[] ModeLong = { "자유 전투: 덤비는 적과 싸워요", "집중 공격: 선택한 대상만 공격해요", "후퇴: 펫들이 싸우지 않고 따라와요" };

    public PlayerController player;
    public CameraRig cam;
    public TamingSystem taming;
    public GameHUD hud;
    public Monster target;
    public int mode;
    public int quest;

    readonly List<PetData> mountList = new List<PetData>();

    void Awake()
    {
        I = this;
        Application.targetFrameRate = 60;
        Screen.orientation = ScreenOrientation.LandscapeLeft;
        Screen.sleepTimeout = SleepTimeout.NeverSleep;

        GameState.Reset();
        Util.ResetCaches();
        ModelLibrary.ResetCache();
        Combatant.All.Clear();
        Monster.AllMonsters.Clear();
        GameHUD.ClearStatic();

        gameObject.AddComponent<TouchInput>();
        hud = gameObject.AddComponent<GameHUD>();
        taming = gameObject.AddComponent<TamingSystem>();

        WorldBuilder.Build();
        SetupLightAndCamera();

        player = PlayerController.Create(WorldBuilder.SpawnPoint);
        cam.target = player;

        Spawner.Create("slime", new Vector3(20f, Y(20f, -45f), -45f), 22f, 5, 1, 2, 15f);
        Spawner.Create("fox", new Vector3(-35f, Y(-35f, -80f), -80f), 20f, 3, 1, 3, 20f);
        Spawner.Create("bird", new Vector3(35f, Y(35f, -95f), -95f), 22f, 3, 1, 3, 20f);
        Spawner.Create("wolf", new Vector3(-130f, Y(-130f, 10f), 10f), 35f, 4, 2, 4, 25f);
        Spawner.Create("lizard", new Vector3(135f, Y(135f, 15f), 15f), 30f, 4, 2, 4, 25f);
        Spawner.Create("griffon", WorldBuilder.NestTop, 0f, 1, 3, 3, 45f);

        // 시작 펫: 불여우 + 첫 비행 탈것 깃털 새
        var fox = new PetData { speciesId = "fox", level = 2 };
        var bird = new PetData { speciesId = "bird", level = 2 };
        GameState.pets.Add(fox);
        GameState.pets.Add(bird);
        SetParty(fox, true);
        SetParty(bird, true);
        GameHUD.Toast("첫 비행 탈것 깃털 새를 받았어요! [탑승]으로 타고 날 수 있어요.", 6f);
        GameHUD.Toast("몬스터를 터치해 선택하고, 체력을 30% 이하로 깎아 테이밍하세요.", 6f);
    }

    static float Y(float x, float z) { return WorldBuilder.Height(x, z); }

    void SetupLightAndCamera()
    {
        Camera c = Camera.main;
        if (c == null)
        {
            var g = new GameObject("Main Camera");
            g.tag = "MainCamera";
            c = g.AddComponent<Camera>();
        }
        c.farClipPlane = 600f;
        c.nearClipPlane = 0.2f;
        c.fieldOfView = 60f;
        cam = c.GetComponent<CameraRig>();
        if (cam == null) cam = c.gameObject.AddComponent<CameraRig>();

        Light sun = null;
#if UNITY_2023_1_OR_NEWER
        var lights = Object.FindObjectsByType<Light>(FindObjectsSortMode.None);
#else
        var lights = Object.FindObjectsOfType<Light>();
#endif
        foreach (var l in lights) if (l.type == LightType.Directional) sun = l;
        if (sun == null)
        {
            sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
        }
        sun.transform.rotation = Quaternion.Euler(50f, -35f, 0f);
        sun.intensity = 1.2f;
        sun.color = new Color(1f, 0.96f, 0.88f);
        sun.shadows = LightShadows.Soft;

        RenderSettings.ambientMode = AmbientMode.Trilight;
        RenderSettings.ambientSkyColor = new Color(0.62f, 0.72f, 0.9f);
        RenderSettings.ambientEquatorColor = new Color(0.55f, 0.6f, 0.62f);
        RenderSettings.ambientGroundColor = new Color(0.35f, 0.33f, 0.3f);
        RenderSettings.fog = true;
        RenderSettings.fogMode = FogMode.Linear;
        RenderSettings.fogColor = new Color(0.72f, 0.83f, 0.95f);
        RenderSettings.fogStartDistance = 160f;
        RenderSettings.fogEndDistance = 450f;
    }

    void Update()
    {
        var h = hud;
        float dt = Time.deltaTime;

        if (target != null && (target.IsDead || target.team != Team.Wild ||
            Vector3.Distance(target.transform.position, player.transform.position) > 70f))
            target = null;

        if (taming.active)
        {
            if (h.Down("bond")) taming.Tap();
        }
        else
        {
            if (h.Down("attack"))
            {
                if (target == null) target = NearestWild(22f);
                if (target == null) GameHUD.Toast("근처에 공격할 몬스터가 없어요.");
                else if (Vector3.Distance(target.transform.position, player.transform.position) > 28f) GameHUD.Toast("대상이 너무 멀어요.");
                else player.Attack(target);
            }
            if (h.Down("tame")) taming.Begin(target);
            if (h.Down("feed")) h.FoodMenu = !h.FoodMenu;
            for (int i = 0; i < 4; i++)
            {
                if (h.Down("food" + i))
                {
                    taming.Feed(target, (Food)i);
                    h.FoodMenu = false;
                }
            }
            if (h.Down("ride"))
            {
                if (player.Riding) player.Dismount();
                else
                {
                    var list = MountList();
                    if (list.Count == 0) GameHUD.Toast("탈 수 있는 펫이 없어요.");
                    else if (list.Count == 1) player.Mount(list[0]);
                    else h.MountMenu = true;
                }
            }
            for (int i = 0; i < 5; i++)
            {
                if (h.Down("mount" + i))
                {
                    var list = MountList();
                    if (i < list.Count) player.Mount(list[i]);
                    h.MountMenu = false;
                }
            }
            if (h.Down("mode"))
            {
                mode = (mode + 1) % 3;
                GameHUD.Toast(ModeLong[mode]);
            }
            if (h.Down("pets")) h.PetPanel = !h.PetPanel;
            if (h.Down("petclose")) h.PetPanel = false;
            for (int i = 0; i < GameState.pets.Count && i < 8; i++)
            {
                if (h.Down("pet" + i))
                {
                    var p = GameState.pets[i];
                    SetParty(p, !p.inParty);
                }
            }
            if (h.Down("target"))
            {
                target = NearestWild(30f);
                if (target == null) GameHUD.Toast("근처에 몬스터가 없어요.");
            }
            int slot = 0;
            foreach (var p in GameState.pets)
            {
                if (!p.inParty) continue;
                if (h.Down("skill" + slot) && p.instance != null) p.instance.UseSkill(target);
                slot++;
                if (slot >= GameState.MaxParty) break;
            }
        }

        // 기절한 펫 회복
        foreach (var p in GameState.pets)
        {
            if (p.reviveTimer <= 0f) continue;
            p.reviveTimer -= dt;
            if (p.reviveTimer <= 0f && p.instance != null && player.mount != p)
            {
                p.instance.Revive(player);
                GameHUD.Toast(Util.IGa(p.Def.name) + " 다시 일어났어요!");
            }
        }

        UpdateQuest();
    }

    // ───────────── 파티 / 탈것 ─────────────
    public void SetParty(PetData p, bool on)
    {
        if (on)
        {
            if (p.inParty) return;
            if (GameState.PartyCount >= GameState.MaxParty)
            {
                GameHUD.Toast("파티는 최대 " + GameState.MaxParty + "마리예요. 먼저 한 마리를 빼세요.");
                return;
            }
            p.inParty = true;
            if (p.instance == null)
            {
                var m = Monster.Create(p.Def, p.level, player.transform.position, p);
                m.TeleportNear(player);
                if (p.reviveTimer > 0f || player.mount == p) m.gameObject.SetActive(false);
            }
        }
        else
        {
            if (!p.inParty) return;
            p.inParty = false;
            if (p.instance != null) Destroy(p.instance.gameObject);
            p.instance = null;
        }
    }

    public int SlotOf(Monster m)
    {
        int i = 0;
        foreach (var p in GameState.pets)
        {
            if (!p.inParty || p.instance == null || !p.instance.gameObject.activeSelf) continue;
            if (p.instance == m) return i;
            i++;
        }
        return 0;
    }

    // 종류별로 레벨이 가장 높은 탈것 하나씩. 비행 단계가 높은 순.
    public List<PetData> MountList()
    {
        mountList.Clear();
        var best = new Dictionary<string, PetData>();
        foreach (var p in GameState.pets)
        {
            if (p.Def.mount == MountType.None) continue;
            PetData b;
            if (!best.TryGetValue(p.speciesId, out b) || p.level > b.level) best[p.speciesId] = p;
        }
        mountList.AddRange(best.Values);
        mountList.Sort((a, b) =>
        {
            if (a.Def.mount != b.Def.mount) return a.Def.mount == MountType.Fly ? -1 : 1;
            return b.Def.flyTier - a.Def.flyTier;
        });
        return mountList;
    }

    // ───────────── 대상 선택 ─────────────
    public void SelectTarget(Monster m)
    {
        target = m;
    }

    Monster NearestWild(float radius)
    {
        Monster best = null;
        float bd = radius * radius;
        foreach (var m in Monster.AllMonsters)
        {
            if (m.team != Team.Wild || m.IsDead) continue;
            float d = (m.transform.position - player.transform.position).sqrMagnitude;
            if (d < bd)
            {
                bd = d;
                best = m;
            }
        }
        return best;
    }

    // ───────────── 이벤트 ─────────────
    static Food LootOf(string id)
    {
        switch (id)
        {
            case "slime": return Food.Jelly;
            case "fox": return Food.Berry;
            case "bird": return Food.Seed;
            default: return Food.Meat;
        }
    }

    public void OnWildKilled(Monster m, Combatant killer)
    {
        if (killer == null || killer.team != Team.Player) return;
        Food f = LootOf(m.def.id);
        int n = Random.Range(1, 3);
        GameState.food[f] += n;
        GameHUD.Popup(m.AimPoint, "+" + GameDB.FoodName(f) + " " + n, new Color(0.7f, 1f, 0.6f));
        if (target == m)
            GameHUD.Toast(Util.EulReul(m.def.name) + " 쓰러뜨렸어요." + (m.everTameable ? " 테이밍하려면 30% 이하에서 멈춰야 해요." : ""));
        float exp = 6f + m.level * 5f;
        foreach (var p in GameState.pets)
            if (p.inParty && p.instance != null) p.instance.GainExp(exp);
    }

    public void OnTamed(Monster m, string detail)
    {
        var p = new PetData { speciesId = m.def.id, level = m.level };
        GameState.pets.Add(p);
        GameDB.RevealedFavorites.Add(m.def.id);
        if (target == m) target = null;
        if (m.spawner != null)
        {
            m.spawner.OnRemoved(m);
            m.spawner = null;
        }
        string msg = "테이밍 성공! " + Util.IGa(m.def.name) + " 동료가 되었어요. " + detail;
        if (GameState.PartyCount < GameState.MaxParty)
        {
            p.inParty = true;
            m.BecomePet(p);
        }
        else
        {
            Destroy(m.gameObject);
            msg += " 파티가 가득 차서 펫 농장으로 보냈어요.";
        }
        GameHUD.Toast(msg, 5f);
        if (m.def.mount != MountType.None)
            GameHUD.Toast(Util.EunNeun(m.def.name) + " 탈 수 있어요! [탑승] 버튼을 눌러 보세요.", 5f);
    }

    // ───────────── 퀘스트 ─────────────
    public string QuestText
    {
        get
        {
            switch (quest)
            {
                case 0: return "젤리 슬라임을 테이밍하세요\n체력을 30% 이하로 깎고 [테이밍]";
                case 1: return "깃털 새를 타고 북동쪽 바위 기둥 위\n그리폰 둥지로 날아가세요";
                case 2: return "그리폰을 테이밍하세요\n좋아하는 먹이를 주면 성공률 UP";
                case 3: return "그리폰을 타고 남서쪽 하늘 섬에\n착륙하세요";
                default: return "프로토타입 클리어!\n자유롭게 탐험하고 테이밍해 보세요";
            }
        }
    }

    public bool HasQuestPos { get { return quest <= 3; } }

    public Vector3 QuestPos
    {
        get
        {
            switch (quest)
            {
                case 0: return new Vector3(20f, WorldBuilder.Height(20f, -45f), -45f);
                case 1:
                case 2: return WorldBuilder.NestTop;
                default: return WorldBuilder.SkyTop;
            }
        }
    }

    void Advance(string msg)
    {
        quest++;
        GameHUD.Toast(msg, 6f);
    }

    void UpdateQuest()
    {
        Vector3 pp = player.transform.position;
        if (quest == 0 && GameState.Owns("slime"))
            Advance("슬라임 테이밍 완료! 이제 [탑승]으로 깃털 새를 타 보세요.");
        else if (quest == 1 && GameState.Owns("griffon"))
            quest = 3;
        else if (quest == 1 && Util.Flat(pp - WorldBuilder.NestTop).magnitude < 15f && pp.y > WorldBuilder.NestTop.y - 2f)
            Advance("그리폰 둥지에 도착! 그리폰을 약하게 만들고 테이밍하세요.");
        else if (quest == 2 && GameState.Owns("griffon"))
            Advance("그리폰 획득! 이제 하늘 섬까지 날 수 있어요. [탑승]에서 그리폰을 고르세요.");
        else if (quest == 3 && Util.Flat(pp - WorldBuilder.SkyTop).magnitude < 24f && pp.y > WorldBuilder.SkyTop.y - 2f)
            Advance("하늘 섬 도착! 프로토타입 클리어!");
    }
}
