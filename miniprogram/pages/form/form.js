const app = getApp();

Page({
  data: {
    t: {},
    p: {},
    visitorTypes: [],
    visitorTypeIndex: 0,
    idTypes: [],
    idTypeIndex: 0,
    visitReasons: [],
    reasonIndex: 0,
    areas: [],
    areaIndex: 0,
    minVisitDate: "",
    noticeItems: [],
    ndaItems: [],
    ndaItemsExternal: [],
    ndaItemsInternal: [],
    noticeChecked: [],
    ndaChecked: [],
    form: {
      applicantName: "",
      applicantCompany: "",
      applicantPhone: "",
      applicantEmail: "",
      visitStartDate: "",
      visitEndDate: "",
      visitTimeSlot: "全天",
      visitPurpose: "业务支持",
      specialRequest: "",
      carPlate: "",
      contactName: "",
      contactPhone: ""
    },
    visitor: {
      name: "",
      company: "",
      phone: "",
      title: "",
      idType: "身份证",
      idNumber: ""
    },
    companions: [],
    showCompanionDialog: false,
    companionIdTypeIndex: 0,
    companionDraft: {
      name: "",
      company: "",
      phone: "",
      title: "",
      idType: "身份证",
      idNumber: ""
    }
  },
  async onLoad() {
    this.applyLocale();
    const config = await app.request("/api/config");
    this.setData({
      minVisitDate: config.minVisitDate,
      "form.visitStartDate": config.minVisitDate,
      "form.visitEndDate": config.minVisitDate,
      "form.applicantName": "访客申请人",
      "form.applicantCompany": "外部访客单位",
      "form.applicantPhone": "13900000000",
      noticeItems: config.visitNoticeItems,
      ndaItems: config.ndaItemsExternal,
      ndaItemsExternal: config.ndaItemsExternal,
      ndaItemsInternal: config.ndaItemsInternal
    });
  },
  onShow() {
    this.applyLocale();
  },
  applyLocale() {
    const t = app.t();
    this.setData({
      t,
      p: t.placeholders,
      visitorTypes: t.visitorTypes,
      idTypes: t.idTypes,
      visitReasons: t.visitReasons,
      areas: t.visitAreas,
      "visitor.idType": t.idTypes[this.data.idTypeIndex || 0],
      "companionDraft.idType": t.idTypes[this.data.companionIdTypeIndex || 0],
      "form.visitPurpose": t.visitReasons[this.data.reasonIndex || 0]
    });
    app.applyLanguage();
    wx.setNavigationBarTitle({ title: t.formTitle });
  },
  onInput(event) {
    this.setData({ [`form.${event.currentTarget.dataset.key}`]: event.detail.value });
  },
  onVisitorInput(event) {
    this.setData({ [`visitor.${event.currentTarget.dataset.key}`]: event.detail.value });
  },
  onVisitorType(event) {
    const index = Number(event.detail.value);
    this.setData({
      visitorTypeIndex: index,
      ndaItems: index === 1 ? this.data.ndaItemsInternal : this.data.ndaItemsExternal,
      ndaChecked: []
    });
  },
  onIdType(event) {
    const index = Number(event.detail.value);
    this.setData({ idTypeIndex: index, "visitor.idType": this.data.idTypes[index] });
  },
  onReason(event) {
    const index = Number(event.detail.value);
    this.setData({ reasonIndex: index, "form.visitPurpose": this.data.visitReasons[index] });
  },
  onArea(event) {
    this.setData({ areaIndex: Number(event.detail.value) });
  },
  onStartDate(event) {
    this.setData({ "form.visitStartDate": event.detail.value, "form.visitEndDate": event.detail.value });
  },
  onEndDate(event) {
    this.setData({ "form.visitEndDate": event.detail.value });
  },
  onNotice(event) {
    this.setData({ noticeChecked: event.detail.value });
  },
  onNda(event) {
    this.setData({ ndaChecked: event.detail.value });
  },
  openCompanion() {
    this.setData({ showCompanionDialog: true });
  },
  closeCompanion() {
    this.setData({ showCompanionDialog: false });
  },
  onCompanionInput(event) {
    this.setData({ [`companionDraft.${event.currentTarget.dataset.key}`]: event.detail.value });
  },
  onCompanionIdType(event) {
    const index = Number(event.detail.value);
    this.setData({ companionIdTypeIndex: index, "companionDraft.idType": this.data.idTypes[index] });
  },
  saveCompanion() {
    const draft = this.data.companionDraft;
    if (!draft.name || !draft.phone || !draft.idNumber) {
      wx.showToast({ title: `${this.data.t.requiredMissing}${this.data.t.companions}${this.data.t.name}、${this.data.t.phone}、${this.data.t.idNumber}`, icon: "none" });
      return;
    }
    const company = draft.company || this.data.visitor.company || this.data.form.applicantCompany || this.data.t.visitorUser;
    this.setData({
      companions: [...this.data.companions, { ...draft, company }],
      companionDraft: { name: "", company: "", phone: "", title: "", idType: this.data.idTypes[0], idNumber: "" },
      companionIdTypeIndex: 0
    });
  },
  removeCompanion(event) {
    const index = Number(event.currentTarget.dataset.index);
    const companions = this.data.companions.filter((_, itemIndex) => itemIndex !== index);
    this.setData({ companions });
  },
  showError(message) {
    wx.showModal({
      title: this.data.t.cannotSubmit,
      content: message,
      showCancel: false
    });
  },
  validateBeforeSubmit() {
    const missing = [];
    const visitor = this.data.visitor;
    const form = this.data.form;
    const t = this.data.t;
    if (!visitor.name) missing.push(t.visitorName);
    if (!visitor.phone) missing.push(t.visitorPhone);
    if (!visitor.company) missing.push(t.companyName);
    if (!visitor.idNumber) missing.push(t.idNumber);
    if (!form.contactName) missing.push(t.contactName);
    if (!form.contactPhone) missing.push(t.contactPhone);
    if (!form.visitStartDate) missing.push(t.startDate);
    if (!form.visitEndDate) missing.push(t.endDate);
    this.data.companions.forEach((item, index) => {
      const label = `${t.companionIndexPrefix}${index + 1}${t.companionIndexSuffix}`;
      if (!item.name) missing.push(`${label}${t.name}`);
      if (!item.phone) missing.push(`${label}${t.phone}`);
      if (!item.company) missing.push(`${label}${t.companyName}`);
      if (!item.idNumber) missing.push(`${label}${t.idNumber}`);
    });
    if (missing.length) return `${t.requiredMissing}：${missing.join("、")}`;
    if (this.data.noticeChecked.length !== this.data.noticeItems.length) {
      return "请完整勾选工厂参观须知";
    }
    if (this.data.ndaChecked.length !== this.data.ndaItems.length) {
      return "请完整勾选保密协议";
    }
    return "";
  },
  async submit() {
    try {
      const validateMessage = this.validateBeforeSubmit();
      if (validateMessage) {
        this.showError(validateMessage);
        return;
      }
      const today = new Date().toISOString().slice(0, 10);
      if (this.data.form.visitStartDate < today) {
        this.showError(this.data.t.startBeforeToday);
        return;
      }
      if (this.data.form.visitEndDate < this.data.form.visitStartDate) {
        this.showError(this.data.t.endBeforeStart);
        return;
      }
      const mainVisitor = {
        ...this.data.visitor,
        company: this.data.visitor.company || this.data.form.applicantCompany
      };
      const payload = {
        ...this.data.form,
        visitorType: this.data.visitorTypes[this.data.visitorTypeIndex],
        applicantName: this.data.visitor.name || this.data.form.applicantName,
        applicantCompany: this.data.visitor.company || this.data.form.applicantCompany,
        applicantPhone: this.data.visitor.phone || this.data.form.applicantPhone,
        contactEmployeeId: "",
        contactName: this.data.form.contactName,
        contactPhone: this.data.form.contactPhone,
        visitAreas: [this.data.areas[this.data.areaIndex]],
        needParking: Boolean(this.data.form.carPlate),
        carPlate: this.data.form.carPlate,
        visitors: [mainVisitor, ...this.data.companions],
        visitNoticeConfirmed: this.data.noticeChecked,
        ndaConfirmed: this.data.ndaChecked
      };
      const result = await app.request("/api/appointments", { method: "POST", data: payload });
      app.globalData.lastApplicationNo = result.applicationNo;
      wx.showToast({ title: this.data.t.successTitle, icon: "success" });
      wx.switchTab({ url: "/pages/index/index" });
    } catch (error) {
      this.showError(error.message);
    }
  }
});
