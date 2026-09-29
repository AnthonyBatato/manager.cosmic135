(() => {
  const blocks = Array.isArray(window.initialBlocks) ? structuredClone(window.initialBlocks) : [];
  const root = document.getElementById('blocks');
  const input = document.getElementById('id_blocks_json');
  const add = document.getElementById('add-block');
  const defaults = type => ({type, title: type === 'hero' ? 'A clear promise for your customer' : type[0].toUpperCase()+type.slice(1), body: 'Write focused, useful copy here.', button: 'Continue', action: type === 'pricing' || type === 'cta' || type === 'hero' ? 'checkout' : '', eyebrow: type === 'hero' ? 'COSMIC135' : '', price: type === 'pricing' ? 'RM 0' : ''});
  const escape = value => String(value ?? '').replace(/[&<>"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
  function render(){
    root.innerHTML = blocks.map((block,index) => `<article class="block-card" data-index="${index}"><div class="block-head"><strong>${escape(block.type)}</strong><div class="block-actions"><button type="button" class="icon-button" data-move="up" aria-label="Move up">↑</button><button type="button" class="icon-button" data-move="down" aria-label="Move down">↓</button><button type="button" class="icon-button danger" data-remove aria-label="Remove">×</button></div></div><div class="block-fields">${block.type==='hero'?`<label>Eyebrow<input data-field="eyebrow" value="${escape(block.eyebrow)}"></label>`:''}<label>Heading<input data-field="title" value="${escape(block.title)}"></label><label>Body<textarea data-field="body">${escape(block.body)}</textarea></label>${block.type==='pricing'?`<label>Price<input data-field="price" value="${escape(block.price)}"></label>`:''}${['hero','pricing','cta'].includes(block.type)?`<label>Button label<input data-field="button" value="${escape(block.button)}"></label><label>Action<select data-field="action"><option value="">No action</option><option value="checkout" ${block.action==='checkout'?'selected':''}>Stripe checkout</option><option value="booking" ${block.action==='booking'?'selected':''}>Booking</option><option value="form" ${block.action==='form'?'selected':''}>Registration form</option><option value="external-checkout" ${block.action==='external-checkout'?'selected':''}>External checkout</option></select></label>`:''}</div></article>`).join('');
    input.value = JSON.stringify(blocks);
  }
  root.addEventListener('input', event => { const card=event.target.closest('[data-index]'); if(!card||!event.target.dataset.field)return; blocks[Number(card.dataset.index)][event.target.dataset.field]=event.target.value; input.value=JSON.stringify(blocks); });
  root.addEventListener('click', event => { const card=event.target.closest('[data-index]'); if(!card)return; const index=Number(card.dataset.index); if(event.target.hasAttribute('data-remove'))blocks.splice(index,1); if(event.target.dataset.move==='up'&&index>0)[blocks[index-1],blocks[index]]=[blocks[index],blocks[index-1]]; if(event.target.dataset.move==='down'&&index<blocks.length-1)[blocks[index+1],blocks[index]]=[blocks[index],blocks[index+1]]; render(); });
  add.addEventListener('change', () => { if(add.value){blocks.push(defaults(add.value)); add.value=''; render();} });
  document.getElementById('builder-form').addEventListener('submit', () => input.value=JSON.stringify(blocks));
  render();
})();
