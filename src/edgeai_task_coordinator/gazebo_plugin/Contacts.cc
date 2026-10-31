// Copyright 2026 EdgeAI Robotics Challenge Team
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// http://www.apache.org/licenses/LICENSE-2.0
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <algorithm>
#include <chrono>
#include <deque>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <gz/plugin/Register.hh>
#include <gz/sim/System.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Collision.hh>
#include <gz/sim/components/ContactSensorData.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/ParentEntity.hh>
#include <gz/msgs/contacts.pb.h>
#include <gz/transport/Node.hh>

namespace edgeai
{
// ContactSensorData is populated by the physics system every step. Unlike the
// stock Contact system, publish an empty, timestamped frame too. Aggregate all
// physics steps between publications so brief contacts are never dropped.
class Contacts : public gz::sim::System,
                 public gz::sim::ISystemConfigure,
                 public gz::sim::ISystemPreUpdate,
                 public gz::sim::ISystemPostUpdate
{
  using ECM = gz::sim::EntityComponentManager;
  using Entity = gz::sim::Entity;
  public: void Configure(const Entity &, const std::shared_ptr<const sdf::Element> &,
                        ECM &, gz::sim::EventManager &) override
  {
    this->instance = std::to_string(std::chrono::system_clock::now().time_since_epoch().count());
    this->pub = this->node.Advertise<gz::msgs::Contacts>("/edgeai/physics_contacts");
  }

  private: std::string Model(Entity entity, const ECM &ecm) const
  {
    std::string model;
    while (entity != gz::sim::kNullEntity)
    {
      if (ecm.Component<gz::sim::components::Model>(entity))
      {
        const auto *name = ecm.Component<gz::sim::components::Name>(entity);
        if (name) model = name->Data();
      }
      const auto *parent = ecm.Component<gz::sim::components::ParentEntity>(entity);
      entity = parent ? parent->Data() : gz::sim::kNullEntity;
    }
    return model;
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &, ECM &ecm) override
  {
    ecm.Each<gz::sim::components::Collision>(
      [&](const Entity &entity, gz::sim::components::Collision *)
      {
        const auto model = this->Model(entity, ecm);
        if (model == "robot_1" || model == "robot_2" ||
            model == "robot_3" || model == "robot_4")
        {
          if (!ecm.Component<gz::sim::components::ContactSensorData>(entity))
            ecm.CreateComponent(entity, gz::sim::components::ContactSensorData());
          this->tracked[entity] = model;
        }
        return true;
      });
  }

  public: void PostUpdate(const gz::sim::UpdateInfo &info, const ECM &ecm) override
  {
    if (info.paused) return;
    const double now = std::chrono::duration<double>(info.simTime).count();
    if (now < this->last)
    {
      this->pending.clear();
      this->ground.clear();
      this->last = now - 1;
    }
    std::map<std::string, int> coverage;
    std::set<std::pair<std::string, std::string>> stepPairs;
    for (auto it = this->tracked.begin(); it != this->tracked.end();)
    {
      const auto entity = it->first;
      const auto model = it->second;
      const auto *data = ecm.Component<gz::sim::components::ContactSensorData>(entity);
      if (!data)
      {
        it = this->tracked.erase(it);
        continue;
      }
      ++it;
      ++coverage[model];
      for (const auto &contact : data->Data().contact())
      {
        const auto otherId = contact.collision1().id() == entity ?
            contact.collision2().id() : contact.collision1().id();
        const auto other = this->Model(otherId, ecm);
        if (other == "ground_plane")
        {
          this->ground.insert(model);
          continue;  // Wheel/floor support is not an arena collision.
        }
        if (other == model) continue;
        const auto first = gz::sim::scopedName(entity, ecm, "::", false);
        const auto second = gz::sim::scopedName(otherId, ecm, "::", false);
        auto key = std::minmax(first, second);
        const auto pair = std::make_pair(key.first, key.second);
        if (stepPairs.insert(pair).second && !this->previousPairs.count(pair))
        {
          ++this->sequence;
          std::ostringstream event;
          event << std::setprecision(17) << "{\"sequence\":" << this->sequence
                << ",\"sim_time\":" << now << ",\"pair\":[" << std::quoted(key.first)
                << "," << std::quoted(key.second) << "]}";
          this->history.push_back(event.str());
          if (this->history.size() > 256) this->history.pop_front();
        }
        auto &saved = this->pending[{key.first, key.second}];
        saved = contact;
        saved.mutable_collision1()->set_name(first);
        saved.mutable_collision2()->set_name(second);
      }
    }
    this->previousPairs = std::move(stepPairs);
    if (now - this->last < 0.05) return;
    gz::msgs::Contacts message;
    auto *header = message.mutable_header();
    header->mutable_stamp()->set_sec(static_cast<int64_t>(now));
    header->mutable_stamp()->set_nsec(static_cast<int32_t>((now - int64_t(now)) * 1e9));
    auto *instanceEntry = header->add_data();
    instanceEntry->set_key("observer_instance");
    instanceEntry->add_value(this->instance);
    auto *sequenceEntry = header->add_data();
    sequenceEntry->set_key("sequence");
    sequenceEntry->add_value(std::to_string(this->sequence));
    for (const auto &event : this->history)
    {
      auto *entry = header->add_data();
      entry->set_key("contact_event");
      entry->add_value(event);
    }
    for (const auto &[model, count] : coverage)
    {
      auto *entry = header->add_data();
      entry->set_key("coverage");
      entry->add_value(model + ":" + std::to_string(count));
    }
    for (const auto &model : this->ground)
    {
      auto *entry = header->add_data();
      entry->set_key("physics_alive");
      entry->add_value(model);
    }
    for (const auto &[key, contact] : this->pending)
      *message.add_contact() = contact;
    this->pub.Publish(message);
    this->pending.clear();
    this->ground.clear();
    this->last = now;
  }

  private: gz::transport::Node node;
  private: gz::transport::Node::Publisher pub;
  private: std::map<Entity, std::string> tracked;
  private: std::map<std::pair<std::string, std::string>, gz::msgs::Contact> pending;
  private: std::set<std::string> ground;
  private: std::set<std::pair<std::string, std::string>> previousPairs;
  private: std::deque<std::string> history;
  private: std::string instance;
  private: uint64_t sequence{0};
  private: double last{-1};
};
}
GZ_ADD_PLUGIN(edgeai::Contacts, gz::sim::System,
              gz::sim::ISystemConfigure, gz::sim::ISystemPreUpdate,
              gz::sim::ISystemPostUpdate)
