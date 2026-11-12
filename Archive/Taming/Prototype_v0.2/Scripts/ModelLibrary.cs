using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

// 실제 3D 모델 연결표. Assets/TamingModels/<몬스터id>/ 에 FBX를 넣으면
// 에디터가 자동으로 이 표(Resources/TamingModelLibrary)를 갱신하고,
// 게임은 해당 몬스터를 도형 대신 그 모델로 그린다. 없으면 기존 도형 그대로.
public class ModelLibrary : ScriptableObject
{
    [System.Serializable]
    public class Entry
    {
        public string id;
        public GameObject prefab;
        public List<AnimationClip> clips = new List<AnimationClip>();
        [Tooltip("모델이 뒤나 옆을 보고 있으면 여기서 돌려 맞춤 (예: 180)")]
        public float yaw;
        [Tooltip("크기 배율 (1 = 기본 크기)")]
        public float heightMul = 1f;
    }

    public List<Entry> entries = new List<Entry>();
    public List<GameObject> trees = new List<GameObject>();
    public List<GameObject> rocks = new List<GameObject>();

    static ModelLibrary cached;
    static bool loaded;

    public static ModelLibrary I
    {
        get
        {
            if (!loaded)
            {
                loaded = true;
                cached = Resources.Load<ModelLibrary>("TamingModelLibrary");
            }
            return cached;
        }
    }

    public static void ResetCache()
    {
        loaded = false;
        cached = null;
    }

    public static Entry Find(string id)
    {
        var lib = I;
        if (lib == null) return null;
        foreach (var e in lib.entries)
            if (e != null && e.prefab != null && e.id == id) return e;
        return null;
    }

    // 모델을 parent 아래에 만들고, 발이 parent 원점에 닿고 키가 targetHeight가 되도록 맞춘다
    public static GameObject Spawn(GameObject prefab, Transform parent, float targetHeight, float yaw)
    {
        var g = Instantiate(prefab, parent, false);
        g.transform.localPosition = Vector3.zero;
        g.transform.localRotation = Quaternion.Euler(0f, yaw, 0f);
        foreach (var c in g.GetComponentsInChildren<Collider>(true)) DestroyImmediate(c);
        foreach (var t in g.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = 2;

        Bounds b;
        if (!MeasureBounds(g, out b)) return g;
        float ps = Mathf.Max(0.0001f, parent.lossyScale.y);
        float h = b.size.y / ps;
        float k = targetHeight / Mathf.Max(0.01f, h);
        g.transform.localScale = g.transform.localScale * k;
        if (MeasureBounds(g, out b))
        {
            float minLocal = (b.min.y - parent.position.y) / ps;
            g.transform.localPosition = new Vector3(0f, -minLocal, 0f);
        }
        return g;
    }

    public static bool MeasureBounds(GameObject g, out Bounds b)
    {
        b = new Bounds();
        bool any = false;
        foreach (var r in g.GetComponentsInChildren<Renderer>())
        {
            if (!any) { b = r.bounds; any = true; }
            else b.Encapsulate(r.bounds);
        }
        return any;
    }
}

// FBX에 들어 있는 애니메이션을 이름으로 찾아 상태에 맞게 섞어 재생한다 (Animator Controller 불필요)
public class ModelAnimator : MonoBehaviour
{
    const int Idle = 0, Walk = 1, Run = 2, Fly = 3, Atk = 4, Sit = 5, Count = 6;

    PlayableGraph graph;
    AnimationMixerPlayable mixer;
    readonly AnimationClipPlayable[] plays = new AnimationClipPlayable[Count];
    readonly AnimationClip[] clips = new AnimationClip[Count];
    readonly float[] weights = new float[Count];
    int state;
    float attackLeft;

    public static ModelAnimator Setup(GameObject model, List<AnimationClip> list)
    {
        if (model == null || list == null || list.Count == 0) return null;
        var anim = model.GetComponentInChildren<Animator>();
        if (anim == null) anim = model.AddComponent<Animator>();
        anim.applyRootMotion = false;
        anim.cullingMode = AnimatorCullingMode.CullUpdateTransforms;
        var ma = model.AddComponent<ModelAnimator>();
        ma.Init(anim, list);
        return ma;
    }

    // 키워드를 포함하는 클립 중 이름이 가장 짧은 것 (예: "Crouch_Idle"보다 "Idle"을 우선)
    static AnimationClip FindClip(List<AnimationClip> list, string[] keys)
    {
        foreach (var k in keys)
        {
            AnimationClip best = null;
            foreach (var c in list)
                if (c != null && c.name.ToLower().Contains(k) && (best == null || c.name.Length < best.name.Length)) best = c;
            if (best != null) return best;
        }
        return null;
    }

    void Init(Animator anim, List<AnimationClip> list)
    {
        clips[Idle] = FindClip(list, new[] { "idle" }) ?? list[0];
        clips[Walk] = FindClip(list, new[] { "walk" }) ?? clips[Idle];
        clips[Run] = FindClip(list, new[] { "run", "jog", "gallop", "sprint" }) ?? clips[Walk];
        clips[Fly] = FindClip(list, new[] { "fly", "flying", "glide", "jump" }) ?? clips[Idle];
        clips[Atk] = FindClip(list, new[] { "attack", "punch", "bite", "spell", "cast", "shoot", "sword", "headbutt" }) ?? clips[Idle];
        clips[Sit] = FindClip(list, new[] { "ride", "sit" }) ?? clips[Idle];

        graph = PlayableGraph.Create(name + "_anim");
        graph.SetTimeUpdateMode(DirectorUpdateMode.GameTime);
        mixer = AnimationMixerPlayable.Create(graph, Count);
        for (int i = 0; i < Count; i++)
        {
            plays[i] = AnimationClipPlayable.Create(graph, clips[i]);
            graph.Connect(plays[i], 0, mixer, i);
            weights[i] = i == Idle ? 1f : 0f;
            mixer.SetInputWeight(i, weights[i]);
        }
        var output = AnimationPlayableOutput.Create(graph, "out", anim);
        output.SetSourcePlayable(mixer);
        graph.Play();
    }

    public void SetState(float move01, bool flying, bool riding)
    {
        if (riding) state = Sit;
        else if (flying) state = Fly;
        else if (move01 > 0.6f) state = Run;
        else if (move01 > 0.08f) state = Walk;
        else state = Idle;
    }

    public void Attack()
    {
        if (!graph.IsValid()) return;
        plays[Atk].SetTime(0.0);
        attackLeft = Mathf.Max(0.3f, clips[Atk].length);
    }

    void Update()
    {
        if (!graph.IsValid()) return;
        float dt = Time.deltaTime;
        attackLeft -= dt;
        int s = attackLeft > 0f ? Atk : state;
        for (int i = 0; i < Count; i++)
        {
            weights[i] = Mathf.MoveTowards(weights[i], i == s ? 1f : 0f, dt * 8f);
            mixer.SetInputWeight(i, weights[i]);
        }
    }

    void OnDestroy()
    {
        if (graph.IsValid()) graph.Destroy();
    }
}
