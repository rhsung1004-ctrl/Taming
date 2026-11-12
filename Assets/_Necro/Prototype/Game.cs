using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace Necro.Proto
{
    // 프로토타입 자동 시작: 기본 씬(SampleScene)이나 이름이 Proto로 시작하는 씬에서 Play를 누르면
    // 씬에 아무것도 놓지 않아도 게임 전체를 코드로 만든다. 본편 씬에서는 동작하지 않는다.
    public static class Bootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init()
        {
            string n = SceneManager.GetActiveScene().name;
            if (!(string.IsNullOrEmpty(n) || n == "SampleScene" || n.StartsWith("Proto"))) return;
            if (Game.I != null) return;
            new GameObject("ProtoGame").AddComponent<Game>();
        }
    }

    public class Game : MonoBehaviour
    {
        public static Game I;

        public PlayerCtl player;
        public Camera cam;
        public Army army;
        public bool paused = true;
        public bool started;
        public int quest;

        bool keeperKilled, dragonKilled;
        float dragonRevive;

        void Awake()
        {
            I = this;
            Application.targetFrameRate = 120;
            Time.timeScale = 0f;

            Util.ResetCaches();
            Combatant.All.Clear();
            Unit.Units.Clear();
            Corpse.All.Clear();
            Hud.ClearStatic();

            gameObject.AddComponent<In>();
            gameObject.AddComponent<Hud>();

            World.Build();
            SetupLightAndCamera();

            player = PlayerCtl.Create(World.SpawnPoint);
            cam.GetComponent<OrbitCam>().target = player;
            army = new Army(this);

            // 버려진 묘지
            Spawner.Create("skeleton", World.At(World.StartXZ, 22f, 28f), 13f, 6, 22f);
            Spawner.Create("wolf", World.At(World.StartXZ, -42f, -6f), 15f, 4, 25f);
            Spawner.Create("archer", World.At(World.StartXZ, 52f, -18f), 12f, 3, 28f);
            Spawner.Create("skeleton", World.At(World.StartXZ, 52f, -18f), 12f, 3, 28f);
            // 납골당: 묘지기
            Spawner.Create("boss", World.At(World.CryptXZ, 0f, -2f), 1f, 1, 0f);
            Spawner.Create("skeleton", World.At(World.CryptXZ, 0f, -8f), 9f, 4, 40f);
            Spawner.Create("archer", World.At(World.CryptXZ, 0f, -8f), 9f, 2, 40f);
            // 잿빛 폐허: 망령 기사
            Spawner.Create("knight", World.At(World.RuinsXZ), 20f, 3, 50f);
            Spawner.Create("archer", World.At(World.RuinsXZ), 24f, 4, 35f);
            Spawner.Create("skeleton", World.At(World.RuinsXZ), 24f, 5, 30f);
            // 용의 무덤
            Spawner.Create("dragon", World.At(World.RoostXZ), 1f, 1, 0f);
            // 부유 성채
            Spawner.Create("archer", World.SkyTop, 14f, 5, 0f, "sky");
            Spawner.Create("skeleton", World.SkyTop, 14f, 5, 0f, "sky");
            Spawner.Create("knight", World.SkyTop, 9f, 2, 0f, "sky");
        }

        void SetupLightAndCamera()
        {
            cam = Camera.main;
            if (cam == null)
            {
                var g = new GameObject("Main Camera");
                g.tag = "MainCamera";
                cam = g.AddComponent<Camera>();
            }
            Color dusk = new Color(0.1f, 0.09f, 0.17f);
            cam.farClipPlane = 700f;
            cam.nearClipPlane = 0.2f;
            cam.fieldOfView = 62f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = dusk;
            if (cam.GetComponent<OrbitCam>() == null) cam.gameObject.AddComponent<OrbitCam>();

            Light moon = null;
#if UNITY_2023_1_OR_NEWER
            var lights = Object.FindObjectsByType<Light>(FindObjectsSortMode.None);
#else
            var lights = Object.FindObjectsOfType<Light>();
#endif
            foreach (var l in lights) if (l.type == LightType.Directional) moon = l;
            if (moon == null)
            {
                moon = new GameObject("Moon").AddComponent<Light>();
                moon.type = LightType.Directional;
            }
            moon.transform.rotation = Quaternion.Euler(46f, -35f, 0f);
            moon.intensity = 1.15f;
            moon.color = new Color(0.7f, 0.74f, 1f);
            moon.shadows = LightShadows.Soft;

            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.3f, 0.29f, 0.45f);
            RenderSettings.ambientEquatorColor = new Color(0.24f, 0.22f, 0.32f);
            RenderSettings.ambientGroundColor = new Color(0.12f, 0.1f, 0.14f);
            RenderSettings.reflectionIntensity = 0.25f;
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogColor = dusk;
            RenderSettings.fogStartDistance = 70f;
            RenderSettings.fogEndDistance = 430f;
        }

        void Update()
        {
            // 일시정지: 처음 시작할 때, Esc/P를 눌렀을 때. 화면을 클릭하면 계속한다.
            if (paused)
            {
                if (In.ClickDown || In.JumpDown || (started && In.PauseDown)) SetPaused(false);
                return;
            }
            if (In.PauseDown) { SetPaused(true); return; }
            if (!In.CursorLocked && In.ClickDown) In.LockCursor(true);    // 에디터에서 Esc로 커서가 풀렸을 때

            float dt = Time.deltaTime;
            army.Tick(dt);

            if (dragonRevive > 0f)
            {
                dragonRevive -= dt;
                if (dragonRevive <= 0f && army.dragon != null && !player.Riding)
                {
                    army.dragon.Revive(player);
                    Hud.Toast("본드래곤이 다시 모였어요.", 3f);
                }
            }
            UpdateQuest();
        }

        void SetPaused(bool on)
        {
            paused = on;
            Time.timeScale = on ? 0f : 1f;
            In.LockCursor(!on);
            if (!on && !started)
            {
                started = true;
                Hud.Toast("…봉인이 풀렸네. 망자들의 목소리는 그대로 들려.", 5f);
                Hud.Toast("마우스 왼쪽으로 영혼 화살을 쏴 해골 병사를 쓰러뜨리세요.", 6f);
            }
        }

        // ───────────── 이벤트 ─────────────
        public void OnEnemyKilled(Unit u)
        {
            player.AddXp(u.def.xp);
            if (u.def.grade == UnitGrade.Hero)
            {
                army.bonusSlots += 2;
                if (u.def.id == "boss" && !keeperKilled)
                {
                    keeperKilled = true;
                    Hud.Toast("묘지기를 쓰러뜨렸어요! 영혼 슬롯 +2", 4f);
                    Hud.Toast("영웅의 시체는 E를 길게 눌러 지배할 수 있어요.", 6f);
                }
            }
            else if (u.def.grade == UnitGrade.Boss)
            {
                army.bonusSlots += 6;
                dragonKilled = true;
                Hud.Toast("고룡이 쓰러졌어요! 영혼 슬롯 +6", 5f);
            }
        }

        public void OnRaised(Unit u)
        {
            if (u.def.mount)
            {
                Hud.Toast("내 뒤로 오렴. 오늘부터 네가 내 날개야. — 본드래곤 획득!", 6f);
                Hud.Toast("V를 누르면 본드래곤에 올라탑니다.", 6f);
            }
            else if (army.Count == 1) Hud.Toast("첫 소환수! 군단은 알아서 싸우고, F로 명령을 바꿀 수 있어요.", 5f);
        }

        public void OnBoneDragonDown()
        {
            dragonRevive = 20f;
            Hud.Toast("본드래곤이 흩어졌어요. 20초 뒤 다시 모입니다.", 4f);
        }

        int SkyLeft()
        {
            int n = 0;
            foreach (var u in Unit.Units)
                if (u.team == Team.Enemy && u.group == "sky" && u.Alive) n++;
            return n;
        }

        // ───────────── 퀘스트 ─────────────
        public string QuestText
        {
            get
            {
                switch (quest)
                {
                    case 0: return "해골 병사를 쓰러뜨리고 시체를 지배하세요 [E]\n군단 " + army.Count + " / 3";
                    case 1: return "북쪽 납골당의 묘지기를 쓰러뜨리세요\n군단이 많을수록 쉬워요";
                    case 2: return "북동쪽 용의 무덤에서 고룡을 쓰러뜨리세요\n동쪽 폐허의 망령 기사를 지배해 가면 좋아요";
                    case 3: return "고룡의 시체 앞에서 E를 길게 눌러\n본드래곤을 만드세요";
                    case 4: return "V로 본드래곤에 올라\n남서쪽 하늘의 부유 성채로 날아가세요";
                    case 5: return "부유 성채의 적을 섬멸하세요 (남은 적 " + SkyLeft() + ")\n하늘에서 브레스로, 또는 착륙해 군단으로";
                    default: return "프로토타입 클리어!\n왕관 조각을 되찾았어요. 자유롭게 돌아다녀 보세요";
                }
            }
        }

        public bool HasQuestPos { get { return quest >= 1 && quest <= 5; } }

        public Vector3 QuestPos
        {
            get
            {
                switch (quest)
                {
                    case 1: return World.At(World.CryptXZ);
                    case 2:
                    case 3: return World.At(World.RoostXZ);
                    default: return World.SkyTop;
                }
            }
        }

        void UpdateQuest()
        {
            if (quest == 0 && (army.Count >= 3 || keeperKilled)) Advance("군단이 모였어요. 이제 납골당의 묘지기를 노려 봐요.");
            if (quest == 1 && keeperKilled) Advance(null);
            if (quest == 2 && dragonKilled) Advance(null);
            if (quest <= 3 && army.dragon != null) { quest = 4; }
            if (quest == 4 && Util.Flat(player.transform.position - World.SkyTop).magnitude < 60f && player.transform.position.y > World.SkyHeight - 15f)
                Advance("부유 성채에 도착! 하늘에서 브레스를 퍼붓거나, 착륙해서 군단을 불러내세요.");
            if (quest == 5 && SkyLeft() == 0) Advance("부유 성채 함락! 프로토타입 클리어!");
        }

        void Advance(string msg)
        {
            quest++;
            if (msg != null) Hud.Toast(msg, 6f);
        }
    }
}
