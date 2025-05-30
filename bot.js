const { Client, GatewayIntentBits, EmbedBuilder } = require("discord.js")
const axios = require("axios")
const fs = require("fs")
const path = require("path")

// Yapılandırma dosyasını yükle
let config = {}
try {
  const configPath = path.join(__dirname, "config.json")
  if (fs.existsSync(configPath)) {
    config = JSON.parse(fs.readFileSync(configPath, "utf8"))
  } else {
    // Varsayılan yapılandırma
    config = {
      token: "DISCORD_BOT_TOKEN_HERE",
      prefix: "!",
      apiUrl: "http://localhost:5000",
      logChannelId: null,
    }
    // Yapılandırma dosyasını oluştur
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2))
    console.log("Varsayılan yapılandırma dosyası oluşturuldu: config.json")
    console.log("Lütfen Discord bot token'ınızı config.json dosyasına ekleyin.")
  }
} catch (error) {
  console.error("Yapılandırma dosyası yüklenirken hata:", error)
  process.exit(1)
}

// Discord bot istemcisi oluştur
const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent],
})

// API ile iletişim için yardımcı fonksiyonlar
const api = {
  async getStatus() {
    try {
      const response = await axios.get(`${config.apiUrl}/status`)
      return response.data
    } catch (error) {
      console.error("API hatası (getStatus):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async getLinks() {
    try {
      const response = await axios.get(`${config.apiUrl}/links`)
      return response.data
    } catch (error) {
      console.error("API hatası (getLinks):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async startLink(link, profileId = null, allProfiles = false) {
    try {
      const response = await axios.post(`${config.apiUrl}/start`, {
        link,
        profile_id: profileId,
        all_profiles: allProfiles,
      })
      return response.data
    } catch (error) {
      console.error("API hatası (startLink):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async stopLink(link = null, profileId = null) {
    try {
      const response = await axios.post(`${config.apiUrl}/stop`, {
        link,
        profile_id: profileId,
      })
      return response.data
    } catch (error) {
      console.error("API hatası (stopLink):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async addLink(url, name = null) {
    try {
      const response = await axios.post(`${config.apiUrl}/links`, { url, name })
      return response.data
    } catch (error) {
      console.error("API hatası (addLink):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async removeLink(link) {
    try {
      const response = await axios.delete(`${config.apiUrl}/links`, { data: { link } })
      return response.data
    } catch (error) {
      console.error("API hatası (removeLink):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async setInterval(minutes) {
    try {
      const response = await axios.put(`${config.apiUrl}/interval`, { minutes })
      return response.data
    } catch (error) {
      console.error("API hatası (setInterval):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async restart() {
    try {
      const response = await axios.post(`${config.apiUrl}/restart`)
      return response.data
    } catch (error) {
      console.error("API hatası (restart):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async reposition() {
    try {
      const response = await axios.post(`${config.apiUrl}/reposition`)
      return response.data
    } catch (error) {
      console.error("API hatası (reposition):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async getProfiles() {
    try {
      const response = await axios.get(`${config.apiUrl}/profiles`)
      return response.data
    } catch (error) {
      console.error("API hatası (getProfiles):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async getLogs(lines = 10) {
    try {
      const response = await axios.get(`${config.apiUrl}/logs?lines=${lines}`)
      return response.data
    } catch (error) {
      console.error("API hatası (getLogs):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },

  async openLink(link, profileId) {
    try {
      const response = await axios.post(`${config.apiUrl}/open`, { link, profile_id: profileId })
      return response.data
    } catch (error) {
      console.error("API hatası (openLink):", error.message)
      return { success: false, message: "API ile iletişim kurulamadı" }
    }
  },
}

// Bot hazır olduğunda
client.once("ready", () => {
  console.log(`Bot olarak giriş yapıldı: ${client.user.tag}`)

  // API bağlantısını kontrol et
  api
    .getStatus()
    .then((status) => {
      if (status.success) {
        console.log("API bağlantısı başarılı")
        console.log(`Aktif link sayısı: ${status.active_count}`)
        console.log(`Toplam link sayısı: ${status.total_count}`)
        console.log(`Kontrol aralığı: ${status.check_interval} dakika`)
      } else {
        console.error("API bağlantısı başarısız")
      }
    })
    .catch((error) => {
      console.error("API bağlantısı kontrol edilirken hata:", error.message)
    })
})

// Mesaj alındığında
client.on("messageCreate", async (message) => {
  // Bot mesajlarını ve prefix olmayan mesajları yoksay
  if (message.author.bot || !message.content.startsWith(config.prefix)) return

  // Komutu ve argümanları ayır
  const args = message.content.slice(config.prefix.length).trim().split(/ +/)
  const command = args.shift().toLowerCase()

  // Komutları işle
  switch (command) {
    case "links":
      await handleLinksCommand(message)
      break

    case "start":
      await handleStartCommand(message, args)
      break

    case "stop":
      await handleStopCommand(message, args)
      break

    case "addlink":
      await handleAddLinkCommand(message, args)
      break

    case "removelink":
      await handleRemoveLinkCommand(message, args)
      break

    case "status":
      await handleStatusCommand(message)
      break

    case "setinterval":
      await handleSetIntervalCommand(message, args)
      break

    case "help":
      await handleHelpCommand(message)
      break

    case "setlogchannel":
      await handleSetLogChannelCommand(message)
      break

    case "restart":
      await handleRestartCommand(message)
      break

    case "reposition":
      await handleRepositionCommand(message)
      break

    case "log":
      await handleLogCommand(message, args)
      break

    case "profiles":
      await handleProfilesCommand(message)
      break

    case "open":
      await handleOpenCommand(message, args)
      break
  }
})

// Komut işleyicileri
async function handleLinksCommand(message) {
  const response = await api.getLinks()

  if (!response.success) {
    return message.reply(`❌ Hata: ${response.message}`)
  }

  if (response.links.length === 0) {
    return message.reply("📋 Kayıtlı link bulunmuyor.")
  }

  const embed = new EmbedBuilder()
    .setTitle("📋 Kayıtlı Linkler")
    .setColor("#0099ff")
    .setDescription("Aşağıdaki linkler sisteme kayıtlıdır:")
    .setTimestamp()

  response.links.forEach((link) => {
    const status = link.status === "active" ? "🟢 Aktif" : link.status === "error" ? "🔴 Hata" : "⚪ Pasif"

    embed.addFields({
      name: `${link.id}. ${link.name}`,
      value: `${status}\n${link.url}`,
    })
  })

  return message.reply({ embeds: [embed] })
}

async function handleStartCommand(message, args) {
  if (args.length === 0) {
    return message.reply(
      "❌ Hata: Link kodu veya URL belirtmelisiniz.\nÖrnek: `!start 1` (tüm profillerde) veya `!start 1 2` (sadece 2. profilde)",
    )
  }

  const linkIdOrUrl = args[0]
  let profileId = null
  let allProfiles = true

  // Profil ID belirtilmişse
  if (args.length > 1) {
    profileId = args[1]
    allProfiles = false
  }

  const response = await api.startLink(linkIdOrUrl, profileId, allProfiles)

  if (response.success) {
    return message.reply(`✅ ${response.message}`)
  } else {
    return message.reply(`❌ Hata: ${response.message}`)
  }
}

async function handleStopCommand(message, args) {
  let response

  if (args.length === 0) {
    // Tüm linkleri durdur
    response = await api.stopLink()
  } else if (args.length === 1) {
    // Belirli bir linki tüm profillerde durdur
    const linkIdOrUrl = args[0]
    response = await api.stopLink(linkIdOrUrl)
  } else {
    // Belirli bir linki belirli profilde durdur
    const linkIdOrUrl = args[0]
    const profileId = args[1]
    response = await api.stopLink(linkIdOrUrl, profileId)
  }

  if (response.success) {
    return message.reply(`✅ ${response.message}`)
  } else {
    return message.reply(`❌ Hata: ${response.message}`)
  }
}

async function handleAddLinkCommand(message, args) {
  if (args.length === 0) {
    return message.reply("❌ Hata: URL belirtmelisiniz.\nÖrnek: `!addlink https://www.twitch.tv/example`")
  }

  const url = args[0]

  // İsim belirtilmişse al
  let name = null
  if (args.length > 1) {
    name = args.slice(1).join(" ")
  }

  const response = await api.addLink(url, name)

  if (response.success) {
    return message.reply(`✅ ${response.message}`)
  } else {
    return message.reply(`❌ Hata: ${response.message}`)
  }
}

async function handleRemoveLinkCommand(message, args) {
  if (args.length === 0) {
    return message.reply(
      "❌ Hata: Link kodu veya URL belirtmelisiniz.\nÖrnek: `!removelink 1` veya `!removelink https://www.twitch.tv/example`",
    )
  }

  const linkIdOrUrl = args[0]
  const response = await api.removeLink(linkIdOrUrl)

  if (response.success) {
    return message.reply(`✅ ${response.message}`)
  } else {
    return message.reply(`❌ Hata: ${response.message}`)
  }
}

async function handleStatusCommand(message) {
  const response = await api.getStatus()

  if (!response.success) {
    return message.reply(`❌ Hata: ${response.message}`)
  }

  const embed = new EmbedBuilder()
    .setTitle("📊 Sistem Durumu")
    .setColor("#0099ff")
    .setDescription("Edge Stream Manager durumu:")
    .addFields(
      { name: "Aktif Link Sayısı", value: `${response.active_count}`, inline: true },
      { name: "Toplam Link Sayısı", value: `${response.total_count}`, inline: true },
      { name: "Kontrol Aralığı", value: `${response.check_interval} dakika`, inline: true },
    )
    .setTimestamp()

  if (response.active_count > 0) {
    embed.addFields({ name: "Aktif Linkler", value: "---", inline: false })

    response.active_links.forEach((link) => {
      embed.addFields({
        name: `${link.id}. ${link.name}`,
        value: `Profil: ${link.profile_name} (ID: ${link.profile_id})\n${link.url}`,
        inline: false,
      })
    })
  }

  // Son kontrol zamanı
  if (response.last_status_check > 0) {
    const lastCheck = new Date(response.last_status_check * 1000).toLocaleString()
    embed.addFields({ name: "Son Kontrol Zamanı", value: lastCheck, inline: false })
  }

  return message.reply({ embeds: [embed] })
}

async function handleSetIntervalCommand(message, args) {
  if (args.length === 0) {
    return message.reply("❌ Hata: Dakika değeri belirtmelisiniz.\nÖrnek: `!setinterval 5`")
  }

  const minutes = args[0]
  const response = await api.setInterval(minutes)

  if (response.success) {
    return message.reply(`✅ ${response.message}`)
  } else {
    return message.reply(`❌ Hata: ${response.message}`)
  }
}

async function handleHelpCommand(message) {
  const embed = new EmbedBuilder()
    .setTitle("🔍 Yardım")
    .setColor("#0099ff")
    .setDescription("Kullanılabilir komutlar:")
    .addFields(
      { name: `${config.prefix}links`, value: "Kayıtlı tüm linkleri listeler", inline: false },
      {
        name: `${config.prefix}start [link] [profil_id]`,
        value: "Linki başlatır (profil_id yoksa tüm profillerde)",
        inline: false,
      },
      {
        name: `${config.prefix}stop [link] [profil_id]`,
        value: "Linki durdurur (boş bırakılırsa tüm linkler)",
        inline: false,
      },
      { name: `${config.prefix}restart`, value: "Tüm aktif linkleri yeniden başlatır", inline: false },
      { name: `${config.prefix}reposition`, value: "Açık pencereleri yeniden hizalar", inline: false },
      {
        name: `${config.prefix}open [link] [profil_id]`,
        value: "Belirtilen linki sadece belirtilen profilde açar",
        inline: false,
      },
      { name: `${config.prefix}addlink [URL] [isim]`, value: "Yeni link ekler (isim opsiyonel)", inline: false },
      { name: `${config.prefix}removelink [link]`, value: "Belirtilen linki siler", inline: false },
      { name: `${config.prefix}profiles`, value: "Tanımlı profilleri listeler", inline: false },
      { name: `${config.prefix}status`, value: "Sistem durumunu gösterir", inline: false },
      {
        name: `${config.prefix}log [satır_sayısı]`,
        value: "Son log kayıtlarını gösterir (varsayılan: 10)",
        inline: false,
      },
      { name: `${config.prefix}setinterval [dakika]`, value: "Kontrol aralığını değiştirir", inline: false },
      { name: `${config.prefix}setlogchannel`, value: "Mevcut kanalı log kanalı olarak ayarlar", inline: false },
      { name: `${config.prefix}help`, value: "Bu yardım mesajını gösterir", inline: false },
    )
    .setTimestamp()

  return message.reply({ embeds: [embed] })
}

async function handleSetLogChannelCommand(message) {
  config.logChannelId = message.channel.id

  // Yapılandırmayı kaydet
  try {
    fs.writeFileSync(path.join(__dirname, "config.json"), JSON.stringify(config, null, 2))
    return message.reply(`✅ Bu kanal log kanalı olarak ayarlandı.`)
  } catch (error) {
    console.error("Yapılandırma kaydedilirken hata:", error)
    return message.reply(`❌ Hata: Yapılandırma kaydedilemedi.`)
  }
}

async function handleRestartCommand(message) {
  const response = await api.restart()

  if (response.success) {
    return message.reply(`✅ ${response.message}`)
  } else {
    return message.reply(`❌ Hata: ${response.message}`)
  }
}

async function handleRepositionCommand(message) {
  const response = await api.reposition()

  if (response.success) {
    return message.reply(`✅ ${response.message}`)
  } else {
    return message.reply(`❌ Hata: ${response.message}`)
  }
}

async function handleLogCommand(message, args) {
  const lines = args.length > 0 ? Number.parseInt(args[0]) || 10 : 10

  if (lines < 1 || lines > 50) {
    return message.reply("❌ Hata: Log satır sayısı 1-50 arasında olmalıdır.")
  }

  const response = await api.getLogs(lines)

  if (!response.success) {
    return message.reply(`❌ Hata: ${response.message}`)
  }

  if (response.logs.length === 0) {
    return message.reply("📋 Log kaydı bulunmuyor.")
  }

  const embed = new EmbedBuilder()
    .setTitle(`📋 Son ${response.logs.length} Log Kaydı`)
    .setColor("#0099ff")
    .setDescription("```\n" + response.logs.join("\n") + "\n```")
    .setTimestamp()

  return message.reply({ embeds: [embed] })
}

async function handleProfilesCommand(message) {
  const response = await api.getProfiles()

  if (!response.success) {
    return message.reply(`❌ Hata: ${response.message}`)
  }

  if (response.profiles.length === 0) {
    return message.reply("📋 Tanımlı profil bulunmuyor.")
  }

  const embed = new EmbedBuilder()
    .setTitle("📋 Tanımlı Profiller")
    .setColor("#0099ff")
    .setDescription("Aşağıdaki profiller sisteme tanımlıdır:")
    .setTimestamp()

  response.profiles.forEach((profile) => {
    embed.addFields({
      name: `${profile.id}. ${profile.name}`,
      value: profile.path,
      inline: false,
    })
  })

  return message.reply({ embeds: [embed] })
}

async function handleOpenCommand(message, args) {
  if (args.length < 2) {
    return message.reply(
      "❌ Hata: Link kodu ve profil ID belirtmelisiniz.\nÖrnek: `!open 1 2` (1. linki 2. profilde aç)",
    )
  }

  const linkIdOrUrl = args[0]
  const profileId = args[1]

  const response = await api.openLink(linkIdOrUrl, profileId)

  if (response.success) {
    return message.reply(`✅ ${response.message}`)
  } else {
    return message.reply(`❌ Hata: ${response.message}`)
  }
}

// Log mesajı gönderme fonksiyonu
async function sendLogMessage(message, type = "info") {
  if (!config.logChannelId) return

  try {
    const channel = await client.channels.fetch(config.logChannelId)
    if (!channel) return

    const embed = new EmbedBuilder().setDescription(message).setTimestamp()

    switch (type) {
      case "error":
        embed.setColor("#ff0000").setTitle("🔴 Hata")
        break
      case "warning":
        embed.setColor("#ffaa00").setTitle("🟡 Uyarı")
        break
      case "success":
        embed.setColor("#00ff00").setTitle("🟢 Başarılı")
        break
      default:
        embed.setColor("#0099ff").setTitle("ℹ️ Bilgi")
    }

    await channel.send({ embeds: [embed] })
  } catch (error) {
    console.error("Log mesajı gönderilirken hata:", error)
  }
}

// Hata yakalama
client.on("error", (error) => {
  console.error("Discord bot hatası:", error)
  sendLogMessage(`Discord bot hatası: ${error.message}`, "error")
})

process.on("unhandledRejection", (error) => {
  console.error("İşlenmemiş promise reddi:", error)
  sendLogMessage(`İşlenmemiş hata: ${error.message}`, "error")
})

// Bot'u başlat
if (!config.token || config.token === "DISCORD_BOT_TOKEN_HERE") {
  console.error("Discord bot token'ı config.json dosyasında belirtilmemiş!")
  console.log("Lütfen config.json dosyasını düzenleyerek bot token'ınızı ekleyin.")
  process.exit(1)
}

client.login(config.token)

// Periyodik API durumu kontrolü
setInterval(async () => {
  try {
    const status = await api.getStatus()
    if (!status.success) {
      console.log("API bağlantısı kesildi")
      sendLogMessage("Python programı ile bağlantı kesildi", "warning")
    }
  } catch (error) {
    console.error("API durumu kontrol edilirken hata:", error)
  }
}, 60000) // Her dakika kontrol et

console.log("Discord bot başlatılıyor...")
console.log(`Prefix: ${config.prefix}`)
console.log(`API URL: ${config.apiUrl}`)
