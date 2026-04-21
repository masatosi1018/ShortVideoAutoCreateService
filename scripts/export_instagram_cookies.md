# Instagram クッキー取得手順

1. 捨てアカウントで Chrome から Instagram にログインします。
2. Chrome 拡張 `Get cookies.txt LOCALLY` をインストールします。
3. Instagram を開いた状態でクッキーを `cookies.txt` として書き出します。
4. このファイルを `config/instagram_cookies.txt` に保存します。
5. 次のコマンドで権限を絞ります。

```bash
chmod 600 config/instagram_cookies.txt
```

## 運用ルール

- 本アカウントとは分離してください。
- BAN 前提で、凍結時はクッキー差し替えだけで復旧できるようにします。
- 連続ダウンロードは 2〜5 秒の間隔を保ってください。
- メールアドレスやパスワードは README、GitHub、`.env.example` に書かないでください。
- ログイン情報の共有が必要でも、GitHub ではなく 1Password などの安全な経路を使ってください。
