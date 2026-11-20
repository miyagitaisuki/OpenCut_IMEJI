//! A mascot in the corner of the lesson: a chibi who changes pose with each
//! sentence. The poses are whole pictures on one canvas (`avatar.json` of
//! `apps/intro` pose sheets); the project keeps only which pose from when.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::{Cue, Error, Project, Result, resolve, ruby};

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum Corner {
    #[default]
    BottomRight,
    BottomLeft,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Mascot {
    /// Folder of the avatar: holds `avatar.json` with a `poses` map.
    pub avatar: PathBuf,
    #[serde(default)]
    pub corner: Corner,
    /// Height as a fraction of the canvas height.
    #[serde(default = "default_height")]
    pub height: f64,
    /// Pose from `time` on (sorted). She shows from the first cue to the last.
    #[serde(default)]
    pub timeline: Vec<MascotPose>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct MascotPose {
    pub time: f64,
    pub pose: String,
}

fn default_height() -> f64 {
    0.55
}

impl Mascot {
    pub fn new(avatar: PathBuf) -> Self {
        Self {
            avatar,
            corner: Corner::default(),
            height: default_height(),
            timeline: Vec::new(),
        }
    }

    /// Pose name -> picture, from the avatar's `avatar.json`.
    pub fn poses(&self, base: &Path) -> Result<BTreeMap<String, PathBuf>> {
        let folder = resolve(base, &self.avatar);
        let manifest = folder.join("avatar.json");
        let text = std::fs::read_to_string(&manifest).map_err(|source| Error::Io {
            path: manifest.clone(),
            source,
        })?;
        let json: serde_json::Value =
            serde_json::from_str(&text).map_err(|source| Error::Json {
                path: manifest.clone(),
                source,
            })?;
        let poses = json
            .get("poses")
            .and_then(|p| p.as_object())
            .ok_or_else(|| Error::Invalid(format!("{}: no \"poses\" map", manifest.display())))?;
        Ok(poses
            .iter()
            .filter_map(|(name, file)| Some((name.clone(), folder.join(file.as_str()?))))
            .collect())
    }

    /// The pose at `time` and the one before it with when this one began.
    pub fn pose_at(&self, time: f64) -> Option<(&str, Option<&str>, f64)> {
        let i = self.timeline.iter().rposition(|p| p.time <= time)?;
        let previous = i.checked_sub(1).map(|j| self.timeline[j].pose.as_str());
        Some((&self.timeline[i].pose, previous, self.timeline[i].time))
    }
}

/// Fills `mascot.timeline` with a pose for every subtitle cue.
pub fn assign_poses(project: &mut Project, base: &Path) -> Result<usize> {
    let Some(mascot) = project.mascot.as_ref() else {
        return Err(Error::Invalid("the project has no mascot".into()));
    };
    let available: Vec<String> = mascot.poses(base)?.into_keys().collect();
    if available.is_empty() {
        return Err(Error::Invalid("the avatar has no poses".into()));
    }
    let timeline = timeline_for(&project.subtitles, &available);
    let count = timeline.len();
    project.mascot.as_mut().expect("checked above").timeline = timeline;
    Ok(count)
}

pub fn timeline_for(cues: &[Cue], available: &[String]) -> Vec<MascotPose> {
    let mut out: Vec<MascotPose> = Vec::new();
    for (i, cue) in cues.iter().enumerate() {
        let sentence = ruby::to_plain(&cue.text);
        let previous = out.last().map(|p| p.pose.as_str());
        let pose = pick_pose(&sentence, available, previous, i);
        out.push(MascotPose {
            time: cue.start,
            pose,
        });
    }
    out
}

// First match wins. Names are the keys of a pose sheet's `poses`; a pose the
// avatar lacks is skipped. (The same rules as apps/intro/src/poses.ts.)
const RULES: &[(&[&str], &[&str])] = &[
    (
        &[
            "こんにちは",
            "こんばんは",
            "おはよう",
            "はじめまして",
            "ようこそ",
            "みなさん",
        ],
        &["wave"],
    ),
    (&["さようなら", "またね", "次回"], &["wave", "hand_chest"]),
    (
        &["ありがとう", "ご視聴", "ご清聴"],
        &["thanks_hands_together", "bow_eyes_closed"],
    ),
    (
        &["すみません", "ごめん", "申し訳"],
        &["sorry_sweat", "bow_eyes_closed"],
    ),
    (
        &["えっ", "びっくり", "驚", "本当に", "ほんとうに"],
        &["surprised"],
    ),
    (
        &["なるほど", "わかりました", "分かりました", "そうか"],
        &["happy_fist_chest", "idea_finger_up"],
    ),
    (
        &["残念", "悲しい", "かなしい", "寂しい", "さびしい", "つらい"],
        &["sad_rub_eye"],
    ),
    (
        &[
            "すばらしい",
            "素晴らしい",
            "正解",
            "よくできました",
            "上手",
            "いいですね",
            "おめでとう",
        ],
        &["clap_happy", "thumbs_up", "cheer_arms_up", "peace_sign"],
    ),
    (
        &["大丈夫", "だいじょうぶ", "オッケー", "OK"],
        &["ok_signs", "thumbs_up"],
    ),
    (&["頑張", "がんば"], &["cheer_fists", "cheer_arms_up"]),
    (
        &["うれしい", "嬉しい", "よかった", "安心"],
        &["content_hand_chest", "hand_chest"],
    ),
    (
        &[
            "違います",
            "ちがいます",
            "間違",
            "ダメ",
            "だめ",
            "いけません",
            "不正解",
        ],
        &["wrong_cross_arms", "scratch_head", "arms_crossed"],
    ),
    (
        &[
            "難しい",
            "むずかしい",
            "わかりません",
            "分かりません",
            "できません",
        ],
        &["worried_hands_up", "shrug_open_palms", "scratch_head"],
    ),
    (
        &["注意", "気をつけ", "気を付け"],
        &["finger_up_talk", "idea_finger_up"],
    ),
    (
        &["質問", "答えて", "どちら", "どれ"],
        &["hold_mic", "ask_finger_chin"],
    ),
    (
        &["聞いて", "聞き", "聴いて", "聴き", "音声", "リスニング"],
        &["hand_ear_smile"],
    ),
    (&["もしもし", "電話", "メール", "スマホ"], &["hold_phone"]),
    (&["ページ", "テキスト", "教科書", "読んで"], &["read_book"]),
    (
        &["考え", "思います", "思う", "かもしれ"],
        &["think_chin", "ask_finger_chin"],
    ),
    (
        &["大切", "大事", "重要", "ポイント", "覚え", "コツ"],
        &["idea_finger_up", "one_finger_up"],
    ),
    (
        &["例えば", "たとえば", "例文"],
        &["present_side", "present_left"],
    ),
    (
        &["ましょう", "ください", "お願い"],
        &["present_open", "peace_sign"],
    ),
    (
        &["今日は", "今日の", "文法", "勉強"],
        &["one_finger_up", "finger_up_talk"],
    ),
];

const NEUTRAL: &[&str] = &[
    "present_left",
    "present_open",
    "finger_up_talk",
    "point_right",
    "present_side",
    "point_left",
    "one_finger_up",
];

fn is_question(sentence: &str) -> bool {
    let s = sentence.trim_end_matches(['。', '！', '!', ' ']);
    s.ends_with('？') || s.ends_with('?') || s.ends_with("ですか") || s.ends_with("ますか")
}

/// A pose for one sentence; not `previous` again, only from `available`.
pub fn pick_pose(
    sentence: &str,
    available: &[String],
    previous: Option<&str>,
    index: usize,
) -> String {
    let has = |p: &str| available.iter().any(|a| a == p);
    let choose = |list: &[&str]| -> Option<String> {
        let ok: Vec<&str> = list.iter().copied().filter(|p| has(p)).collect();
        ok.iter()
            .find(|p| Some(**p) != previous)
            .or(ok.first())
            .map(|p| (*p).to_owned())
    };
    if is_question(sentence)
        && let Some(p) = choose(&["ask_finger_chin", "think_chin", "hold_mic"])
    {
        return p;
    }
    for (words, poses) in RULES {
        if words.iter().any(|w| sentence.contains(w))
            && let Some(p) = choose(poses)
            && Some(p.as_str()) != previous
        {
            return p;
        }
    }
    let neutral: Vec<&String> = NEUTRAL
        .iter()
        .filter_map(|n| available.iter().find(|a| a.as_str() == *n))
        .collect();
    let pool: Vec<&String> = if neutral.is_empty() {
        available.iter().collect()
    } else {
        neutral
    };
    for i in 0..pool.len() {
        let p = pool[(index + i) % pool.len()];
        if Some(p.as_str()) != previous {
            return p.clone();
        }
    }
    pool[0].clone()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn names(list: &[&str]) -> Vec<String> {
        list.iter().map(|s| (*s).to_owned()).collect()
    }

    #[test]
    fn picks_by_what_is_said() {
        let all = names(&[
            "wave",
            "ask_finger_chin",
            "cheer_arms_up",
            "bow_eyes_closed",
            "present_left",
            "present_open",
        ]);
        assert_eq!(pick_pose("みなさん、こんにちは。", &all, None, 0), "wave");
        assert_eq!(
            pick_pose("これは何ですか？", &all, None, 0),
            "ask_finger_chin"
        );
        assert_eq!(pick_pose("正解です！", &all, None, 0), "cheer_arms_up");
        assert_eq!(
            pick_pose("ありがとうございました。", &all, None, 0),
            "bow_eyes_closed"
        );
    }

    #[test]
    fn never_repeats_and_skips_missing_poses() {
        let few = names(&["present_left", "present_open"]);
        assert_eq!(pick_pose("正解です！", &few, None, 0), "present_left");
        assert_eq!(
            pick_pose("普通の文です。", &few, Some("present_left"), 0),
            "present_open"
        );
        let wave = names(&["wave", "present_left"]);
        assert_eq!(
            pick_pose("ようこそ。", &wave, Some("wave"), 0),
            "present_left"
        );
    }

    #[test]
    fn timeline_has_a_pose_per_cue_and_strips_furigana() {
        let cue = |start: f64, text: &str| Cue {
            start,
            end: start + 1.0,
            text: text.into(),
            role: None,
            translation: None,
        };
        let all = names(&["wave", "present_left", "present_open"]);
        let t = timeline_for(
            &[
                cue(0.0, "こんにちは。"),
                cue(1.0, "今日{きょう}は勉強{べんきょう}。"),
            ],
            &all,
        );
        assert_eq!(t.len(), 2);
        assert_eq!(t[0].pose, "wave");
        assert_ne!(t[0].pose, t[1].pose);
    }

    #[test]
    fn pose_at_finds_the_current_and_previous() {
        let mut m = Mascot::new("x".into());
        m.timeline = vec![
            MascotPose {
                time: 0.0,
                pose: "a".into(),
            },
            MascotPose {
                time: 2.0,
                pose: "b".into(),
            },
        ];
        assert_eq!(m.pose_at(1.0), Some(("a", None, 0.0)));
        assert_eq!(m.pose_at(2.5), Some(("b", Some("a"), 2.0)));
        assert_eq!(m.pose_at(-1.0), None);
    }
}
