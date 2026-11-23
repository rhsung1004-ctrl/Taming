using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace Necro.EditorTools
{
    // 월드 데이터(world.json, trees.json, objects.json, manifest.json)를 읽는 작은 JSON 해석기.
    // Unity의 JsonUtility 는 배열 안의 배열([[0, 1.5, 2.0], ...])이나 사전을 읽지 못해서 직접 만든다.
    // 결과: 객체 = Dictionary<string, object>, 배열 = List<object>, 숫자 = double, 문자열 = string, true/false = bool, null = null
    public static class NecroJson
    {
        public static object Parse(string text)
        {
            var p = new Parser(text);
            p.SkipWs();
            object v = p.Value();
            p.SkipWs();
            if (!p.End) throw p.Error("값 뒤에 알 수 없는 글자가 있습니다");
            return v;
        }

        class Parser
        {
            readonly string s;
            int i;
            public Parser(string text) { s = text ?? ""; }
            public bool End { get { return i >= s.Length; } }

            public FormatException Error(string msg)
            {
                int line = 1, col = 1;
                for (int k = 0; k < i && k < s.Length; k++)
                {
                    if (s[k] == '\n') { line++; col = 1; }
                    else col++;
                }
                return new FormatException(msg + " (" + line + "번째 줄 " + col + "번째 글자)");
            }

            public void SkipWs()
            {
                while (i < s.Length)
                {
                    char c = s[i];
                    if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '﻿') i++;
                    else break;
                }
            }

            public object Value()
            {
                if (End) throw Error("값이 있어야 할 곳에서 파일이 끝났습니다");
                char c = s[i];
                if (c == '{') return Obj();
                if (c == '[') return Arr();
                if (c == '"') return Str();
                if (c == 't') { Word("true"); return true; }
                if (c == 'f') { Word("false"); return false; }
                if (c == 'n') { Word("null"); return null; }
                if (c == '-' || (c >= '0' && c <= '9')) return Num();
                throw Error("알 수 없는 값 '" + c + "'");
            }

            void Word(string w)
            {
                if (string.CompareOrdinal(s, i, w, 0, w.Length) != 0) throw Error("'" + w + "' 가 와야 합니다");
                i += w.Length;
            }

            Dictionary<string, object> Obj()
            {
                var d = new Dictionary<string, object>();
                i++;
                SkipWs();
                if (!End && s[i] == '}') { i++; return d; }
                while (true)
                {
                    SkipWs();
                    if (End || s[i] != '"') throw Error("객체의 이름(\"...\")이 와야 합니다");
                    string key = Str();
                    SkipWs();
                    if (End || s[i] != ':') throw Error("':' 가 와야 합니다");
                    i++;
                    SkipWs();
                    d[key] = Value();
                    SkipWs();
                    if (End) throw Error("객체가 닫히지 않았습니다 ('}' 없음)");
                    if (s[i] == ',') { i++; continue; }
                    if (s[i] == '}') { i++; return d; }
                    throw Error("',' 또는 '}' 가 와야 합니다");
                }
            }

            List<object> Arr()
            {
                var a = new List<object>();
                i++;
                SkipWs();
                if (!End && s[i] == ']') { i++; return a; }
                while (true)
                {
                    SkipWs();
                    a.Add(Value());
                    SkipWs();
                    if (End) throw Error("배열이 닫히지 않았습니다 (']' 없음)");
                    if (s[i] == ',') { i++; continue; }
                    if (s[i] == ']') { i++; return a; }
                    throw Error("',' 또는 ']' 가 와야 합니다");
                }
            }

            string Str()
            {
                i++;
                var sb = new StringBuilder();
                while (true)
                {
                    if (End) throw Error("문자열이 닫히지 않았습니다");
                    char c = s[i++];
                    if (c == '"') return sb.ToString();
                    if (c != '\\') { sb.Append(c); continue; }
                    if (End) throw Error("문자열이 닫히지 않았습니다");
                    char e = s[i++];
                    switch (e)
                    {
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        case 'u':
                            if (i + 4 > s.Length) throw Error("\\u 뒤에 16진수 4자리가 와야 합니다");
                            sb.Append((char)Convert.ToInt32(s.Substring(i, 4), 16));
                            i += 4;
                            break;
                        default: throw Error("알 수 없는 이스케이프 '\\" + e + "'");
                    }
                }
            }

            double Num()
            {
                int start = i;
                if (s[i] == '-') i++;
                while (i < s.Length && "0123456789.eE+-".IndexOf(s[i]) >= 0) i++;
                double v;
                if (!double.TryParse(s.Substring(start, i - start), NumberStyles.Float, CultureInfo.InvariantCulture, out v))
                    throw Error("숫자를 읽을 수 없습니다 '" + s.Substring(start, i - start) + "'");
                return v;
            }
        }
    }

    // 읽은 JSON에서 값을 꺼내는 도우미. 틀린 곳은 errors 에 한국어로 모은다 (한 번에 다 보여 주려고).
    public class JsonReadContext
    {
        public readonly List<string> errors = new List<string>();
        public readonly string file;
        public JsonReadContext(string file) { this.file = file; }

        public void Fail(string where, string msg) { errors.Add(file + " → " + where + ": " + msg); }

        public static bool IsNum(object o) { return o is double || o is int || o is long || o is float; }
        public static double ToNum(object o) { return Convert.ToDouble(o, CultureInfo.InvariantCulture); }

        public Dictionary<string, object> Obj(object o, string where)
        {
            var d = o as Dictionary<string, object>;
            if (d == null) Fail(where, "객체({ ... })가 아닙니다");
            return d;
        }

        public List<object> Arr(Dictionary<string, object> d, string key, string where, bool required)
        {
            object o;
            if (d == null || !d.TryGetValue(key, out o) || o == null)
            {
                if (required) Fail(where, "'" + key + "' 배열이 없습니다");
                return null;
            }
            var a = o as List<object>;
            if (a == null) Fail(where, "'" + key + "' 가 배열([ ... ])이 아닙니다");
            return a;
        }

        public bool Has(Dictionary<string, object> d, string key) { return d != null && d.ContainsKey(key) && d[key] != null; }

        public double Num(Dictionary<string, object> d, string key, string where, double fallback, bool required)
        {
            object o;
            if (d == null || !d.TryGetValue(key, out o) || o == null)
            {
                if (required) Fail(where, "'" + key + "' 숫자가 없습니다");
                return fallback;
            }
            if (!IsNum(o)) { Fail(where, "'" + key + "' 가 숫자가 아닙니다"); return fallback; }
            return ToNum(o);
        }

        public string Str(Dictionary<string, object> d, string key, string where, string fallback, bool required)
        {
            object o;
            if (d == null || !d.TryGetValue(key, out o) || o == null)
            {
                if (required) Fail(where, "'" + key + "' 글자가 없습니다");
                return fallback;
            }
            var s = o as string;
            if (s == null) { Fail(where, "'" + key + "' 가 글자(\"...\")가 아닙니다"); return fallback; }
            return s;
        }

        public bool Bool(Dictionary<string, object> d, string key, bool fallback)
        {
            object o;
            if (d == null || !d.TryGetValue(key, out o) || !(o is bool)) return fallback;
            return (bool)o;
        }

        // 숫자 n 개짜리 배열 → float[]. 없거나 틀리면 null
        public float[] Floats(object o, int n, string where)
        {
            var a = o as List<object>;
            if (a == null || a.Count < n) { Fail(where, "숫자 " + n + "개짜리 배열이 와야 합니다"); return null; }
            var r = new float[n];
            for (int k = 0; k < n; k++)
            {
                if (!IsNum(a[k])) { Fail(where, (k + 1) + "번째 값이 숫자가 아닙니다"); return null; }
                r[k] = (float)ToNum(a[k]);
            }
            return r;
        }

        public float[] Floats(Dictionary<string, object> d, string key, int n, string where, bool required)
        {
            object o;
            if (d == null || !d.TryGetValue(key, out o) || o == null)
            {
                if (required) Fail(where, "'" + key + "' (숫자 " + n + "개 배열)가 없습니다");
                return null;
            }
            return Floats(o, n, where + "." + key);
        }

        public Vector3 Vec3(Dictionary<string, object> d, string key, string where, Vector3 fallback, bool required)
        {
            var f = Floats(d, key, 3, where, required);
            return f == null ? fallback : new Vector3(f[0], f[1], f[2]);
        }

        public Color Col(Dictionary<string, object> d, string key, string where, Color fallback, bool required)
        {
            var f = Floats(d, key, 3, where, required);
            return f == null ? fallback : new Color(f[0], f[1], f[2]);
        }
    }
}
