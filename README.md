# EG Tool Auto-Switch

エレコム製ゲーミングマウス／キーボード設定ソフト「EG Tool」のプロファイルを、現在アクティブなアプリケーション（ゲームなど）に合わせて**自動的に切り替える**常駐ツールです。

EG Toolには「アプリケーション連動機能」が標準ではない（または機能しない）場合でも、このツールを使うことで自動切り替えを実現できます。

## 特徴
- **完全バックグラウンド動作**: タスクトレイに常駐し、作業の邪魔になりません。
- **設定ファイル (`config.json`)**: 切り替えルールを自由に編集可能。
- **リロード機能**: アプリを再起動せずに設定変更を反映可能。
- **軽量**: Python製で、exe化すればPython環境がないPCでも動作します。

## 動作環境
- Windows 10 / 11
- [ELECOM EG Tool](https://www.elecom.co.jp/support/download/peripheral/mouse/eg_tool/) がインストール・起動されていること。

## 使い方（一般ユーザー向け）

### 1. インストール
1. [Releases](../../releases) ページから `EG_AutoSwitch.exe` をダウンロードします。
2. 任意のフォルダに配置してください。

### 2. 設定 (`config.json`)
初回起動時に `config.json` が自動生成されます。
このファイルをメモ帳などで開き、自分の環境に合わせて編集してください。

```json
{
    "default_profile": 1, 
    "mappings": {
        "league of legends.exe": 2,
        "valorant.exe": 3
    },
    "ignore_processes": [
        "elecomui.exe", "python.exe", "powershell.exe", "cmd.exe"
    ]
}
```
- `default_profile`: どのゲームも起動していないときのプロファイル番号 (1~3)。
- `mappings`: 「プロセス名 (.exe)」と「切り替えたいプロファイル番号」のペア。
  - プロセス名はタスクマネージャーの詳細タブなどで確認してください（すべて小文字で記述してください）。
- `ignore_processes`: 無視するシステムプロセス（通常は変更不要）。

### 3. 起動
`EG_AutoSwitch.exe` を右クリックし、**「管理者として実行」** してください。
※EG Toolを操作するために管理者権限が必須です。

起動するとタスクトレイ（画面右下の時計付近）に青と赤のアイコンが表示されます。

### 4. 操作
タスクトレイアイコンを右クリックするとメニューが出ます。
- **Open Config**: 設定ファイルをテキストエディタで開きます。
- **Reload Config**: 設定ファイルを書き換えた後に押すと、再起動なしで反映されます。
- **Exit**: ツールを終了します。

---

## 開発者向け（ソースコードからビルドする場合）

### 必要要件
- Python 3.x
- 以下のライブラリ:
  ```bash
  pip install pywin32 pywinauto pystray pillow
  ```

### 実行
```bash
python auto_switch.py
```

### exe化（ビルド）
PyInstallerを使用します。
```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name "EG_AutoSwitch" --clean --icon=NONE auto_switch.py
```
`dist/` フォルダに `EG_AutoSwitch.exe` が生成されます。

## ライセンス
MIT License
