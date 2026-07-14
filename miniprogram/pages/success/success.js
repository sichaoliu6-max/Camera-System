const app = getApp();

Page({
  data: { applicationNo: "", t: {} },
  onLoad(query) {
    this.setData({ applicationNo: query.applicationNo || app.globalData.lastApplicationNo });
  },
  onShow() {
    this.setData({ t: app.t() });
    app.applyLanguage();
    wx.setNavigationBarTitle({ title: app.t().successTitle });
  },
  goDetail() {
    wx.navigateTo({ url: `/pages/detail/detail?applicationNo=${this.data.applicationNo}` });
  }
});
