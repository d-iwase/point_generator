# IFC点群生成ツール

IFCモデルの表面から点群を生成するWindows向けGUIツールです．IFCからOBJとMTLへの変換，OBJからの点群生成，両方を続けて実行する一括生成に対応します．3D表示機能はありません．

## 動作環境とインストール

- Windows，Python 3.12，Tkinter
- NumPy 2.4.6，IfcOpenShell 0.8.5

```powershell
python3.12.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

TkinterはPythonの標準配布に含まれるものを使用します．`start.bat` と `start.vbs` は，`python3.12.exe` がPATHから見つかる環境向けです．

## 使い方

1. 「IFCから点群まで一括生成」タブで，密度，１回の処理点数，RGBとラベルの有無，変換設定を指定します．
2. 「IFCを選んで一括生成」を押し，入力IFCと出力OBJの保存先を選びます．
3. 同じフォルダにOBJ，MTL，`<保存名>_surface.txt` が作成されます．ラベルを有効にした場合は `<保存名>_labels.csv` も作成されます．

「IFCをOBJに変換」タブとOBJからの点群生成機能は個別にも使えます．既存の出力ファイルは上書きしません．中止または失敗時，変換済みのOBJとMTLは残り，生成途中の点群TXTは削除されます．

## 出力と設定

- 点群TXTはヘッダーなし，空白区切りです．RGBとラベルが有効なら `X Y Z R G B LABEL`，RGBのみなら `X Y Z R G B`，RGBを無効にすると `X Y Z` です．
- 座標の単位はメートルです．OBJの１単位を１mとして扱います．IFC変換時の「追加倍率 0.001」は初期設定で有効ですが，IFCの単位に応じて自動で切り替わる設定ではありません．入力モデルの単位を確認してください．
- 「元の向きを保持」が無効なら，XY平面での主方向をX軸に合わせます．原点はモデルの中心へ移動します．
- 点数は表面積×密度を丸めた値で，最低１点です．三角形の表面積に比例した一様ランダムサンプリングを行います．密度の単位は点/m²です．
- RGBはOBJが参照するMTLの `Kd` を使用します．材質色がない面は灰色 `(178, 178, 178)` です．テクスチャ画像と頂点カラーは扱いません．
- ラベルはRGBごとの０始まりの整数です．同じRGBには同じラベルが付きます．IFC要素IDや部材分類を直接表す値ではありません．対応するCSVにはRGB，IFC部材名，IFCクラスなどを記録します．
- 固定点数，ノイズ，dropout，voxel sizeの設定はありません．モデル形状をメモリに保持するため，大きなOBJでは相応のメモリが必要です．

## 開発時の確認

```powershell
python -m unittest discover -s tests -v
```

GUIのスモークテストは `python tests/smoke_gui.py` と `python tests/smoke_ifc_gui.py` で実行できます．画面を操作するため，デスクトップ環境が必要です．
