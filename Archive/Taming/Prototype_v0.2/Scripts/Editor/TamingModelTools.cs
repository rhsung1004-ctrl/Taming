using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

// Assets/TamingModels/ 아래에 FBX를 넣으면:
//  1) 가져오기 설정을 자동으로 맞추고 (player = Humanoid, 몬스터 = Generic, idle/walk/run/fly 반복)
//  2) Resources/TamingModelLibrary 연결표를 자동으로 다시 만든다.
public class TamingModelPostprocessor : AssetPostprocessor
{
    public const string Root = "Assets/TamingModels/";

    static string FolderOf(string path)
    {
        string rest = path.Substring(Root.Length);
        int i = rest.IndexOf('/');
        return i < 0 ? "" : rest.Substring(0, i).ToLower();
    }

    void OnPreprocessModel()
    {
        if (!assetPath.StartsWith(Root)) return;
        var mi = (ModelImporter)assetImporter;
        string folder = FolderOf(assetPath);
        if (folder == "nature")
        {
            mi.animationType = ModelImporterAnimationType.None;
            mi.importAnimation = false;
            return;
        }
        mi.animationType = folder == "player" ? ModelImporterAnimationType.Human : ModelImporterAnimationType.Generic;
        mi.importAnimation = true;
    }

    void OnPreprocessAnimation()
    {
        if (!assetPath.StartsWith(Root)) return;
        var mi = (ModelImporter)assetImporter;
        var clips = mi.defaultClipAnimations;
        if (clips == null || clips.Length == 0) return;
        foreach (var c in clips)
        {
            string n = c.name.ToLower();
            c.loopTime = n.Contains("idle") || n.Contains("walk") || n.Contains("run") || n.Contains("fly") ||
                         n.Contains("gallop") || n.Contains("swim") || n.Contains("sit") || n.Contains("glide");
        }
        mi.clipAnimations = clips;
    }

    static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
    {
        bool touched = false;
        foreach (var p in imported) if (p.StartsWith(Root)) touched = true;
        foreach (var p in deleted) if (p.StartsWith(Root)) touched = true;
        foreach (var p in moved) if (p.StartsWith(Root)) touched = true;
        if (touched)
        {
            EditorApplication.delayCall -= TamingModelTools.Build;
            EditorApplication.delayCall += TamingModelTools.Build;
        }
    }
}

public static class TamingModelTools
{
    const string RootFolder = "Assets/TamingModels";
    const string LibPath = "Assets/Resources/TamingModelLibrary.asset";

    [MenuItem("Tools/Taming/모델 폴더 만들기")]
    public static void MakeFolders()
    {
        if (!AssetDatabase.IsValidFolder(RootFolder)) AssetDatabase.CreateFolder("Assets", "TamingModels");
        string[] ids = { "player", "slime", "fox", "wolf", "bird", "lizard", "griffon", "nature" };
        foreach (var id in ids)
            if (!AssetDatabase.IsValidFolder(RootFolder + "/" + id)) AssetDatabase.CreateFolder(RootFolder, id);
        AssetDatabase.Refresh();
        Debug.Log("[Taming] Assets/TamingModels 아래에 폴더를 만들었어요. 각 폴더에 FBX를 넣으세요.");
    }

    [MenuItem("Tools/Taming/모델 연결 다시 만들기")]
    public static void Build()
    {
        if (!AssetDatabase.IsValidFolder(RootFolder)) return;
        if (!AssetDatabase.IsValidFolder("Assets/Resources")) AssetDatabase.CreateFolder("Assets", "Resources");

        var lib = AssetDatabase.LoadAssetAtPath<ModelLibrary>(LibPath);
        if (lib == null)
        {
            lib = ScriptableObject.CreateInstance<ModelLibrary>();
            AssetDatabase.CreateAsset(lib, LibPath);
        }

        // 사람이 Inspector에서 맞춘 방향·크기 값은 유지
        var keep = new Dictionary<string, ModelLibrary.Entry>();
        foreach (var e in lib.entries) if (e != null && !string.IsNullOrEmpty(e.id)) keep[e.id] = e;
        lib.entries.Clear();
        lib.trees.Clear();
        lib.rocks.Clear();

        foreach (var dir in AssetDatabase.GetSubFolders(RootFolder))
        {
            string id = Path.GetFileName(dir).ToLower();
            string[] guids = AssetDatabase.FindAssets("t:Model", new[] { dir });

            if (id == "nature")
            {
                foreach (var g in guids)
                {
                    string path = AssetDatabase.GUIDToAssetPath(g);
                    var go = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                    if (go == null) continue;
                    string n = Path.GetFileNameWithoutExtension(path).ToLower();
                    if (n.Contains("tree") || n.Contains("pine") || n.Contains("birch")) lib.trees.Add(go);
                    else if (n.Contains("rock") || n.Contains("stone") || n.Contains("boulder")) lib.rocks.Add(go);
                }
                continue;
            }

            var entry = new ModelLibrary.Entry { id = id };
            ModelLibrary.Entry old;
            if (keep.TryGetValue(id, out old))
            {
                entry.yaw = old.yaw;
                entry.heightMul = old.heightMul;
            }
            int bestClipCount = int.MaxValue;
            foreach (var g in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(g);
                var go = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                int clipCount = 0;
                foreach (var a in AssetDatabase.LoadAllAssetsAtPath(path))
                {
                    var clip = a as AnimationClip;
                    if (clip == null || clip.name.StartsWith("__preview__")) continue;
                    entry.clips.Add(clip);
                    clipCount++;
                }
                // 애니메이션 전용 파일보다 '모델 본체' 파일(클립이 적은 쪽)을 우선
                if (go != null && go.GetComponentInChildren<Renderer>(true) != null && clipCount < bestClipCount)
                {
                    entry.prefab = go;
                    bestClipCount = clipCount;
                }
            }
            if (entry.prefab != null) lib.entries.Add(entry);
        }

        EditorUtility.SetDirty(lib);
        AssetDatabase.SaveAssets();
        ModelLibrary.ResetCache();
        Debug.Log("[Taming] 모델 연결 완료: 캐릭터/몬스터 " + lib.entries.Count + "종, 나무 " + lib.trees.Count + "개, 바위 " + lib.rocks.Count + "개");
    }
}
