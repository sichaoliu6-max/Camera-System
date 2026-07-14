const app = getApp();

Page({
  data: { q: "", items: [], t: {} },
  onShow() {
    this.setData({ t: app.t() });
    app.applyLanguage();
    wx.setNavigationBarTitle({ title: app.t().recordsTitle });
    this.load();
  },
  onInput(event) {
    this.setData({ q: event.detail.value });
  },
  async load() {
    const data = await app.request(`/api/appointments?q=${encodeURIComponent(this.data.q)}`);
    this.setData({ items: data.items });
  },
  goDetail(event) {
    wx.navigateTo({ url: `/pages/detail/detail?applicationNo=${event.currentTarget.dataset.no}` });
  }
});
