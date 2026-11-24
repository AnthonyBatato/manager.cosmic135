$ErrorActionPreference = "Stop"

$sourceDirectory = Join-Path $PSScriptRoot "..\workshop-tw-video-upload"
$destinationDirectory = Join-Path $PSScriptRoot "..\workshop-tw-live-upload"
$sourceHtml = Join-Path $sourceDirectory "index.html"
$destinationHtml = Join-Path $destinationDirectory "index.html"

if (Test-Path -LiteralPath $destinationDirectory) {
    throw "Destination already exists: $destinationDirectory"
}

New-Item -ItemType Directory -Path $destinationDirectory | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceDirectory "taipei-promo.mp4") -Destination $destinationDirectory

$html = Get-Content -Raw -LiteralPath $sourceHtml
$html = $html.Replace(
    "<title>數字解碼 × 數靈啟示牌｜看懂你的生命訊息｜TATKEE大師兄 2026.12.19 台灣</title>",
    "<title>直播限定買一送一｜數字解碼 × 數靈啟示牌｜TATKEE大師兄 台灣</title>"
)
$html = $html.Replace(
    '<meta name="description" content="2026年12月19日，TATKEE大師兄台灣一日實體工作坊。數字解碼 × 數靈啟示牌，看懂你的生命訊息，並學會如何為自己挑選門牌、車牌與號碼。">',
    '<meta name="description" content="11月26日直播限定，首5組買一送一。支付 NT$3,980，兩位參加 TATKEE大師兄 2026年12月19日台灣特別工作坊。">'
)
$html = $html.Replace('href="#offer"', 'href="#live-promo"')

$promoCss = @'

/* Livestream-only promotion */
#live-promo{position:relative;overflow:hidden;padding:clamp(48px,8vw,92px) 0;background:radial-gradient(circle at 12% 10%,rgba(226,34,34,.2),transparent 34%),radial-gradient(circle at 88% 90%,rgba(212,168,76,.22),transparent 32%),#100b08;color:#fff}
#live-promo:before{content:"LIVE";position:absolute;right:-.04em;top:-.24em;font-family:var(--serif);font-size:clamp(110px,25vw,360px);font-weight:800;line-height:1;color:rgba(255,255,255,.025);pointer-events:none}
.live-offer{position:relative;display:grid;grid-template-columns:minmax(0,1.15fr) minmax(300px,.85fr);gap:clamp(28px,5vw,64px);align-items:center;padding:clamp(28px,5vw,58px);border:1px solid rgba(232,195,112,.58);border-radius:28px;background:linear-gradient(145deg,rgba(51,22,16,.96),rgba(19,13,10,.96));box-shadow:0 34px 90px rgba(0,0,0,.42)}
.live-kicker{display:inline-flex;align-items:center;gap:10px;margin-bottom:22px;padding:8px 14px;border:1px solid rgba(255,255,255,.22);border-radius:999px;color:#ffe6aa;font-size:14px;font-weight:800;letter-spacing:.12em}
.live-kicker:before{content:"";width:9px;height:9px;border-radius:50%;background:#ff3b30;box-shadow:0 0 0 6px rgba(255,59,48,.14);animation:livePulse 1.4s ease-in-out infinite}
@keyframes livePulse{50%{box-shadow:0 0 0 10px rgba(255,59,48,0)}}
.live-copy h2{margin:0;font-family:var(--serif);font-size:clamp(42px,7vw,82px);line-height:.94;letter-spacing:-.035em}
.live-copy h2 span{display:block;color:#f0c96c}
.live-lead{max-width:680px;margin:25px 0 0;color:rgba(255,255,255,.78);font-size:clamp(17px,2vw,21px);line-height:1.8}
.live-window{display:flex;flex-wrap:wrap;gap:10px;margin-top:25px}
.live-window span{padding:9px 13px;border-radius:10px;background:rgba(255,255,255,.07);color:#f8e6bd;font-weight:750}
.live-deal{padding:clamp(25px,4vw,40px);border-radius:22px;background:#fff;color:#21150f;text-align:center;box-shadow:0 24px 55px rgba(0,0,0,.28)}
.live-limit{display:inline-block;margin-bottom:16px;padding:7px 12px;border-radius:999px;background:#a81717;color:#fff;font-size:14px;font-weight:850;letter-spacing:.08em}
.live-deal h3{margin:0;font-family:var(--serif);font-size:clamp(31px,4vw,48px);line-height:1.05}
.live-value{margin:18px 0 0;color:#7f6d63;text-decoration:line-through;font-weight:700}
.live-price{display:flex;justify-content:center;align-items:flex-end;gap:7px;margin:3px 0 2px;color:#9b6515}
.live-price small{padding-bottom:10px;font-size:17px;font-weight:800}
.live-price strong{font-family:var(--serif);font-size:clamp(58px,8vw,86px);line-height:1}
.live-for-two{margin:0 0 22px;font-size:18px;font-weight:850;color:#8c1d18}
.live-deal .btn{width:100%;justify-content:center}
.live-rule{margin:17px 0 0;color:#75665e;font-size:14px;line-height:1.6}
@media(max-width:820px){.live-offer{grid-template-columns:1fr}.live-copy{text-align:center}.live-lead{margin-left:auto;margin-right:auto}.live-window{justify-content:center}}
'@
$html = $html.Replace("</style>", "$promoCss`r`n</style>")

$promoMarkup = @'

<!-- ===== LIVESTREAM PROMO ===== -->
<section id="live-promo" aria-labelledby="livePromoTitle">
  <div class="shell">
    <div class="live-offer rv">
      <div class="live-copy">
        <div class="live-kicker">11.26 LIVESTREAM EXCLUSIVE</div>
        <h2 id="livePromoTitle">直播限定<span>首 5 組・買一送一</span></h2>
        <p class="live-lead">直播當晚完成付款的前 5 組，支付一位的優惠價，即可獲得兩個 12月19日 台北特別場名額。兩位參加者將分別收到自己的入場券登記連結。</p>
        <div class="live-window" aria-label="Promotion period">
          <span>11月26日</span><span>晚上 8:30 開放</span><span>限首 5 組・售完即止</span>
        </div>
      </div>
      <div class="live-deal">
        <span class="live-limit">僅限首 5 組付款成功訂單</span>
        <h3>一人付款<br>兩人同行</h3>
        <p class="live-value">兩位優惠價 NT$ 7,960</p>
        <div class="live-price"><small>NT$</small><strong>3,980</strong></div>
        <p class="live-for-two">兩個完整參加名額</p>
        <a data-lpm-action="checkout:tw-live-bogo" href="#" class="btn btn-gold">搶先完成付款</a>
        <p class="live-rule">名額以 Stripe 完成付款時間為準；點擊或進入結帳不保留名額。首 5 組付款成功後即停止。</p>
      </div>
    </div>
  </div>
</section>
'@
$marker = "<!-- ===== 02 生命的重複 ===== -->"
if (-not $html.Contains($marker)) {
    throw "Could not find insertion marker in source HTML."
}
$html = $html.Replace($marker, "$promoMarkup`r`n$marker")

[System.IO.File]::WriteAllText($destinationHtml, $html, [System.Text.UTF8Encoding]::new($false))
